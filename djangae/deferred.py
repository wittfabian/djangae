
"""
Google provides the defer() call as a wrapper around the taskqueue API. Unfortunately
it suffers from serious bugs, and "ticking timebomb" API decisions. Specifically:

- defer(_transactional=True) won't work transactionally if your task > 100kb
- A working defer() might suddenly start blowing up inside transactions if the task grows > 100kb
  if you haven't specified xg=True, or you hit the entity group limit

This defer is an adapted version of that one, with the following changes:

- defer() will *always* use an entity group (even if the task is < 100kb) unless you pass
  _small_task=True
- defer(_transactional=True) works
- Adds a _wipe_related_caches option (defaults to True) which wipes out ForeignKey caches
  if you defer Django model instances (which can result in stale data when the deferred task
  runs)
"""

import copy
import logging

from django.db import models
from django.utils import timezone
from google.appengine.api.datastore import Delete
from google.appengine.ext.deferred import PermanentTaskFailure  # noqa

from djangae.db import transaction
from djangae.models import DeferIterationMarker
from djangae.processing import find_key_ranges_for_queryset
from djangae.utils import retry


def _wipe_caches(args, kwargs):
    # Django related fields (E.g. foreign key) store a "cache" of the related
    # object when it's first accessed. These caches can drastically bloat up
    # an instance. If we then defer that instance we're pickling and unpickling a
    # load of data we likely need to reload in the task anyway. This code
    # wipes the caches of related fields if any of the args or kwargs are
    # instances.
    def _wipe_instance(instance):
        for field in (f for f in instance._meta.fields if f.rel):
            cache_name = field.get_cache_name()
            if hasattr(instance, cache_name):
                delattr(instance, cache_name)

    # We have to copy the instances before wiping the caches
    # otherwise the calling code will suddenly lose their cached things
    for i, arg in enumerate(args):
        if isinstance(arg, models.Model):
            args[i] = copy.deepcopy(arg)
            _wipe_instance(args[i])

    for k, v in list(kwargs.items()):
        if isinstance(v, models.Model):
            kwargs[k] = copy.deepcopy(v)
            _wipe_instance(kwargs[k])


def defer(obj, *args, **kwargs):
    """
        This is a replacement for google.appengine.ext.deferred.defer which doesn't
        suffer the bug where tasks are deferred non-transactionally when they hit a
        certain limit.

        It also *always* uses an entity group, unless you pass _small_task=True in which
        case it *never* uses an entity group (but you are limited by 100K)
    """

    from google.appengine.ext.deferred.deferred import (
        run_from_datastore,
        serialize,
        taskqueue,
        _DeferredTaskEntity,
        _DEFAULT_URL,
        _TASKQUEUE_HEADERS,
        _DEFAULT_QUEUE
    )

    KWARGS = {
        "countdown", "eta", "name", "target", "retry_options"
    }

    taskargs = {x: kwargs.pop(("_%s" % x), None) for x in KWARGS}
    taskargs["url"] = kwargs.pop("_url", _DEFAULT_URL)

    transactional = kwargs.pop("_transactional", False)
    small_task = kwargs.pop("_small_task", False)
    wipe_related_caches = kwargs.pop("_wipe_related_caches", True)

    taskargs["headers"] = dict(_TASKQUEUE_HEADERS)
    taskargs["headers"].update(kwargs.pop("_headers", {}))
    queue = kwargs.pop("_queue", _DEFAULT_QUEUE)

    if wipe_related_caches:
        args = list(args)
        _wipe_caches(args, kwargs)
        args = tuple(args)

    pickled = serialize(obj, *args, **kwargs)

    key = None
    try:
        # Always use an entity group unless this has been
        # explicitly marked as a small task
        if not small_task:
            key = _DeferredTaskEntity(data=pickled).put()

        # Defer the task
        task = taskqueue.Task(payload=pickled, **taskargs)
        ret = task.add(queue, transactional=transactional)

        # Delete the key as it wasn't needed
        if key:
            Delete(key)
        return ret

    except taskqueue.TaskTooLargeError:
        if small_task:
            raise

        pickled = serialize(run_from_datastore, str(key))
        task = taskqueue.Task(payload=pickled, **taskargs)

        # This is the line that fixes a bug in the SDK. The SDK
        # code doesn't pass transactional here.
        return task.add(queue, transactional=transactional)
    except:  # noqa
        # Any other exception? Delete the key
        if key:
            Delete(key)
        raise


_TASK_TIME_LIMIT = 10 * 60
_BUFFER_TIME = 15  # Arbitrary but reasonable value


class TimeoutException(Exception):
    "Exception thrown to indicate that a new shard should begin and the current one should end"
    pass


def _process_shard(marker_id, model, query, callback, finalize, queue_name, args):
    args = args or tuple()

    start_time = timezone.now()

    try:
        marker = DeferIterationMarker.objects.get(pk=marker_id)
    except DeferIterationMarker.DoesNotExist:
        logging.warning("DeferIterationMarker with ID: %s has vanished, cancelling task", marker_id)
        return

    # Redefer if the task isn't ready to begin
    if not marker.is_ready:
        defer(
            _process_shard, marker_id, model, query, callback, finalize,
            queue_name=queue_name,
            args=args,
            _queue=queue_name,
            _countdown=1
        )
        return

    try:
        qs = model.objects.all()
        qs.query = query
        qs.order_by("pk")

        last_pk = None
        for instance in qs.all():
            last_pk = instance.pk

            if (timezone.now() - start_time).total_seconds() > _TASK_TIME_LIMIT - _BUFFER_TIME:
                raise TimeoutException()

            callback(instance, *args)
        else:
            with transaction.atomic(xg=True):
                try:
                    marker.refresh_from_db()
                except DeferIterationMarker.DoesNotExist:
                    logging.warning("TaskMarker with ID: %s has vanished, cancelling task", marker_id)
                    return

                marker.shards_complete += 1
                marker.save()

                if marker.shards_complete == marker.shard_count:
                    # Delete the marker if we were asked to
                    if marker.delete_on_completion:
                        marker.delete()

                    defer(
                        finalize,
                        *args,
                        _transactional=True,
                        _queue=queue_name
                    )

    except (Exception, TimeoutException) as e:
        # We intentionally don't catch DeadlineExceededError here. There's not enough time to redefer a task
        # and so the only option is to retry the current shard. It shouldn't happen though, 15 seconds should be
        # ample time... DeadlineExceededError doesn't subclass Exception, it subclasses BaseException so it'll
        # never enter here (if it does occur, somehow)

        if isinstance(e, TimeoutException):
            logging.debug("Ran out of time processing shard. Deferring new shard to continue from: %s", last_pk)
        else:
            logging.exception("Error processing shard. Retrying.")

        if last_pk:
            qs = qs.filter(pk__gte=last_pk)

        defer(
            _process_shard, marker_id, qs.model, qs.query, callback, finalize,
            queue_name=queue_name,
            args=args,
            _queue=queue_name,
            _countdown=1
        )


def _generate_shards(model, query, callback, finalize, args, queue_name, _shards, _delete_marker):
    queryset = model.objects.all()
    queryset.query = query

    key_ranges = find_key_ranges_for_queryset(queryset, _shards)

    marker = DeferIterationMarker.objects.create(delete_on_completion=_delete_marker)

    for i, (start, end) in enumerate(key_ranges):
        is_last = i == (len(key_ranges) - 1)

        qs = model.objects.all()
        qs.query = query

        filter_kwargs = {}
        if start:
            filter_kwargs["pk__gte"] = start

        if end:
            filter_kwargs["pk__lt"] = end

        qs = qs.filter(**filter_kwargs)

        @transaction.atomic(xg=True)
        def make_shard():
            marker.refresh_from_db()
            marker.shard_count += 1
            if is_last:
                marker.is_ready = True
            marker.save()

            defer(
                _process_shard,
                marker.pk,
                qs.model, qs.query, callback, finalize,
                args=args,
                queue_name=queue_name,
                _queue=queue_name,
                _transactional=True
            )

        try:
            retry(make_shard, _attempts=5)
        except:  # noqa
            marker.delete()  # This will cause outstanding tasks to abort
            raise


def defer_iteration_with_finalize(
        queryset, callback, finalize, args=None, _queue='default', _shards=5,
        _delete_marker=True, _transactional=False):

    defer(
        _generate_shards,
        queryset.model,
        queryset.query,
        callback,
        finalize,
        args=args,
        queue_name=_queue,
        _delete_marker=_delete_marker,
        _shards=_shards,
        _queue=_queue,
        _transactional=_transactional
    )
