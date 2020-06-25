
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
import functools
import logging
import os
import pickle
import time
import types
from datetime import timedelta
from urllib.parse import unquote

from djangae.environment import task_queue_name
from djangae.models import DeferIterationMarker
from djangae.processing import find_key_ranges_for_queryset
from djangae.utils import retry
from django.conf import settings
from django.db import (
    connections,
    models,
)
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_str
from gcloudc.db import transaction
from google.protobuf.timestamp_pb2 import Timestamp

from . import (
    CLOUD_TASKS_LOCATION_SETTING,
    cloud_tasks_project,
    get_cloud_tasks_client,
)
from .models import DeferredTask

logger = logging.getLogger(__name__)


DEFERRED_ITERATION_SHARD_INDEX_KEY = "DEFERRED_ITERATION_SHARD_INDEX"

_DEFAULT_QUEUE = "default"
_DEFAULT_URL = reverse_lazy("tasks_deferred_handler")
_TASKQUEUE_HEADERS = {
    "Content-Type": "application/octet-stream"
}


class Error(Exception):
    """Base class for exceptions in this module."""


class PermanentTaskFailure(Error):
    """Indicates that a task failed, and will never succeed."""


class SingularTaskFailure(Error):
    """Indicates that a task failed once."""


def _run_from_datastore(deferred_task_id):
    """
        Retrieves a task from the database and executes it.
    """

    def run(data):
        """
            Unpickles and executes a task.
        """
        try:
            func, args, kwds = pickle.loads(data)
        except Exception as e:
            raise PermanentTaskFailure(e)
        else:
            return func(*args, **kwds)

    entity = DeferredTask.objects.filter(pk=deferred_task_id).first()
    if not entity:
        raise PermanentTaskFailure()

    try:
        run(entity.data)
        entity.delete()
    except PermanentTaskFailure:
        entity.delete()
        raise


def invoke_member(obj, membername, *args, **kwargs):
    return getattr(obj, membername)(*args, **kwargs)


def _curry_callable(obj, *args, **kwargs):
    """
        Takes a callable and arguments and returns a task queue tuple.

        The returned tuple consists of (callable, args, kwargs), and can be pickled
        and unpickled safely.
    """

    if isinstance(obj, types.MethodType):
        return (invoke_member, (obj.__self__, obj.__func__.__name__) + args, kwargs)

    elif isinstance(obj, types.BuiltinMethodType):
        if not obj.__self__:
            return (obj, args, kwargs)
        else:
            return (invoke_member, (obj.__self__, obj.__name__) + args, kwargs)
    elif isinstance(obj, (
        types.FunctionType, types.BuiltinFunctionType, type
    )):
        return (obj, args, kwargs)
    elif hasattr(obj, "__call__"):
        return (obj, args, kwargs)
    else:
        raise ValueError("obj must be callable")


def _wipe_caches(args, kwargs):
    # Django related fields (E.g. foreign key) store a "cache" of the related
    # object when it's first accessed. These caches can drastically bloat up
    # an instance. If we then defer that instance we're pickling and unpickling a
    # load of data we likely need to reload in the task anyway. This code
    # wipes the caches of related fields if any of the args or kwargs are
    # instances.
    def _wipe_instance(instance):
        for field in (f for f in instance._meta.fields if f.remote_field):
            if field.is_cached(instance):
                field.delete_cached_value(instance)

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


def _serialize(obj, *args, **kwargs):
    curried = _curry_callable(obj, *args, **kwargs)
    return pickle.dumps(curried, protocol=pickle.HIGHEST_PROTOCOL)


def _schedule_task(
    project_id, location, queue, pickled_data,
    task_args, small_task, deferred_handler_url, task_headers
):

    client = get_cloud_tasks_client()

    deferred_task = None
    try:
        # Always use an entity group unless this has been
        # explicitly marked as a small task
        if not small_task:
            deferred_task = DeferredTask.objects.create(data=pickled_data)

        queue = queue or _DEFAULT_QUEUE
        path = client.queue_path(project_id, location, queue)

        schedule_time = task_args['eta']
        if task_args['countdown']:
            schedule_time = timezone.now() + timedelta(seconds=task_args['countdown'])

        if schedule_time:
            # If a schedule time has bee requested, we need to convert
            # to a Timestamp
            ts = Timestamp()
            ts.FromDatetime(schedule_time)
            schedule_time = ts

        task = {
            'name': task_args['name'],
            'schedule_time': schedule_time,
            'app_engine_http_request': {  # Specify the type of request.
                'http_method': 'POST',
                'relative_uri': deferred_handler_url,
                'body': pickled_data,
                'headers': task_headers,
            }
        }

        # Defer the task
        task = client.create_task(path, task)  # FIXME: Handle transactional

        # Delete the key as it wasn't needed
        if deferred_task:
            deferred_task.delete()
    except Exception:  # taskqueue.TaskTooLargeError:
        raise  # FIXME: Catch whatever is thrown when a task is > 100kb

        if small_task:
            raise

        pickled = _serialize(_run_from_datastore, deferred_task.pk)

        task = {
            'app_engine_http_request': {  # Specify the type of request.
                'http_method': 'POST',
                'relative_uri': deferred_handler_url,
                'body': pickled
            }
        }

        client.create_task(path, task)  # FIXME: Handle transactional
    except:  # noqa
        # Any other exception? Delete the key
        if deferred_task:
            deferred_task.delete()
        raise


def defer(obj, *args, **kwargs):
    """
        This is a reimplementation of the defer() function that shipped with Google App Engine
        before the Python 3 runtime.

        It fixes a number of bugs in that implementation, but has some subtle differences. In
        particular, the _transactional flag is not entirely atomic - deferred tasks will
        run on successful commit, but they're not *guaranteed* to run if there is an error
        submitting them.

        It also *always* uses an entity group, unless you pass _small_task=True in which
        case it *never* uses an entity group (but you are limited by 100K)
    """

    KWARGS = {
        "countdown", "eta", "name", "target", "retry_options", "transactional", "using"
    }

    task_args = {x: kwargs.pop(("_%s" % x), None) for x in KWARGS}

    if task_args['target'] or task_args['retry_options']:
        raise NotImplementedError("FIXME. Implement these options")

    deferred_handler_url = kwargs.pop("_url", None) or unquote(force_str(_DEFAULT_URL))

    using = task_args["using"] or "default"
    connection = connections[using]

    transactional = (
        task_args["transactional"]
        if task_args["transactional"] is not None
        else connection.in_atomic_block
    )

    small_task = kwargs.pop("_small_task", False)
    wipe_related_caches = kwargs.pop("_wipe_related_caches", True)

    task_headers = dict(_TASKQUEUE_HEADERS)
    task_headers.update(kwargs.pop("_headers", {}))

    queue = kwargs.pop("_queue", _DEFAULT_QUEUE) or _DEFAULT_QUEUE

    if wipe_related_caches:
        args = list(args)
        _wipe_caches(args, kwargs)
        args = tuple(args)

    pickled = _serialize(obj, *args, **kwargs)

    project_id = cloud_tasks_project()
    assert(project_id)  # Should be checked in apps.py ready()

    location = getattr(settings, CLOUD_TASKS_LOCATION_SETTING, None)
    assert(location)  # Should be checked in apps.py

    args = (project_id, location, queue, pickled, task_args, small_task, deferred_handler_url, task_headers)

    if transactional:
        # Django connections have an on_commit message that run things on
        # post-commit.
        connection.on_commit(functools.partial(_schedule_task, *args))
    else:
        _schedule_task(*args)


_TASK_TIME_LIMIT = 10 * 60


class TimeoutException(Exception):
    "Exception thrown to indicate that a new shard should begin and the current one should end"
    pass


def _process_shard(marker_id, shard_number, model, query, callback, finalize, buffer_time, args, kwargs):
    args = args or tuple()

    # Set an index of the shard in the environment, which is useful for callbacks
    # to have access too so they can identify a task
    os.environ[DEFERRED_ITERATION_SHARD_INDEX_KEY] = str(shard_number)

    start_time = time.time()

    try:
        marker = DeferIterationMarker.objects.get(pk=marker_id)
    except DeferIterationMarker.DoesNotExist:
        logger.warning("DeferIterationMarker with ID: %s has vanished, cancelling task", marker_id)
        return

    # Redefer if the task isn't ready to begin
    if not marker.is_ready:
        defer(
            _process_shard, marker_id, shard_number, model, query, callback, finalize,
            buffer_time=buffer_time,
            args=args,
            kwargs=kwargs,
            _queue=task_queue_name().rsplit("/", 1)[-1],
            _countdown=1
        )
        return

    try:
        qs = model.objects.all()
        qs.query = query
        qs.order_by("pk")

        calculate_buffer_time = buffer_time is None
        longest_iteration = 0
        longest_iteration_multiplier = 1.1

        last_pk = None
        for instance in qs.all():
            last_pk = instance.pk

            buffer_time_to_apply = (
                longest_iteration * longest_iteration_multiplier
                if calculate_buffer_time
                else buffer_time
            )

            # The first iteration, buffer_time_to_apply will be zero if buffer_time was None
            # that's not a problem.
            shard_time = (time.time() - start_time)
            if shard_time > _TASK_TIME_LIMIT - buffer_time_to_apply:
                raise TimeoutException()

            iteration_start = time.time()

            callback(instance, *args, **kwargs)

            iteration_end = time.time()
            iteration_time = iteration_end - iteration_start

            # Store the iteration time if it's the longest
            longest_iteration = max(longest_iteration, iteration_time)
        else:
            @transaction.atomic(xg=True)
            def mark_shard_complete():
                try:
                    marker.refresh_from_db()
                except DeferIterationMarker.DoesNotExist:
                    logger.warning(
                        "TaskMarker with ID: %s has vanished, cancelling task",
                        marker_id
                    )
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
                        _queue=task_queue_name().rsplit("/", 1)[-1],
                        **kwargs
                    )

            retry(mark_shard_complete, _attempts=6)

    except (Exception, TimeoutException) as e:
        # We intentionally don't catch DeadlineExceededError here. There's not enough time to redefer a task
        # and so the only option is to retry the current shard. It shouldn't happen though, 15 seconds should be
        # ample time... DeadlineExceededError doesn't subclass Exception, it subclasses BaseException so it'll
        # never enter here (if it does occur, somehow)

        if isinstance(e, TimeoutException):
            logger.debug(
                "Ran out of time processing shard. Deferring new shard to continue from: %s",
                last_pk
            )
        else:
            logger.exception("Error processing shard. Retrying.")

        if last_pk:
            qs = qs.filter(pk__gte=last_pk)

        defer(
            _process_shard, marker_id, shard_number, qs.model, qs.query, callback, finalize,
            buffer_time=buffer_time,
            args=args,
            kwargs=kwargs,
            _queue=task_queue_name().rsplit("/", 1)[-1],
            _countdown=1
        )


def _generate_shards(
    model, query, callback, finalize, args, kwargs, shards, delete_marker, buffer_time
):

    queryset = model.objects.all()
    queryset.query = query

    key_ranges = find_key_ranges_for_queryset(queryset, shards)

    marker = DeferIterationMarker.objects.create(
        delete_on_completion=delete_marker,
        callback_name=callback.__name__,
        finalize_name=finalize.__name__
    )

    for i, (start, end) in enumerate(key_ranges):
        is_last = i == (len(key_ranges) - 1)
        shard_number = i

        qs = model.objects.all()
        qs.query = query

        filter_kwargs = {}
        if start:
            filter_kwargs["pk__gte"] = start

        if end:
            filter_kwargs["pk__lt"] = end

        # calling order_by with no args to clear any pre-existing ordering (e.g. from Meta.ordering)
        qs = qs.filter(**filter_kwargs).order_by()

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
                shard_number,
                qs.model, qs.query, callback, finalize,
                args=args,
                kwargs=kwargs,
                buffer_time=buffer_time,
                _queue=task_queue_name().rsplit("/", 1)[-1],
                _transactional=True
            )

        try:
            retry(make_shard, _attempts=5)
        except:  # noqa
            marker.delete()  # This will cause outstanding tasks to abort
            raise


def defer_iteration_with_finalize(
        queryset, callback, finalize, _queue='default', _shards=5,
        _delete_marker=True, _transactional=False, _buffer_time=None, *args, **kwargs):

    defer(
        _generate_shards,
        queryset.model,
        queryset.query,
        callback,
        finalize,
        args=args,
        kwargs=kwargs,
        delete_marker=_delete_marker,
        shards=_shards,
        buffer_time=_buffer_time,
        _queue=_queue,
        _transactional=_transactional
    )
