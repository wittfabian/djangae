
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

from django.db import models

from google.appengine.api.datastore import Delete
from google.appengine.ext.deferred import (  # noqa
    PermanentTaskFailure,
    SingularTaskFailure
)


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
