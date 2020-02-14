# Deferred

# djangae.tasks.deferred.defer

The App Engine SDK provides a utility function called `defer()` which is used to call
functions and methods from the task queue.

The built-in `defer()` method suffers from a number of issues with both bugs, and the API itself.

`djangae.deferred.defer` is a near-drop-in replacement for `google.appengine.ext.deferred.defer` with a few differences:

 - The code has been altered to always use a Datastore entity group unless the task is explicitly marked as being "small" (less than 100k) with the `_small_task=True` flag.
 - Transactional defers are always transactional, even if the task is > 100k (this is a bug in the original defer)
 - If a Django instance is passed as an argument to the called function, then the foreign key caches are wiped before
   deferring to avoid bloating and stale data when the task runs. This can be disabled with `_wipe_related_caches=False`

Everything else should behave in the same way. The actual running of deferred tasks still uses the Google handler (which is wrapped by Djangae)

# djange.tasks.deferred.defer_iteration_with_finalize

`defer_iteration_with_finalize(queryset, callback, finalize, args=None, _queue='default', _shards=5, _delete_marker=True, _transactional=False)`

This function provides similar functionality to a Mapreduce pipeline, but it's entirely self-contained and leverages
defer to process the tasks.

The function iterates the passed Queryset in shards, calling `callback` on each instance. Once all shards complete then
the `finalize` callback is called. If a shard gets close to the 10-minute deadline, or it hits an unhandled exception it re-defers another shard to continue processing.

`DeadlineExceededError` is explicitly not handled. This is because there is rarely enough time between the exception being caught, and the request being terminated, to correctly defer a new shard.

Each processing task keeps track of its execution time and re-defers itself to avoid hitting App Engine's `DeadlineExceededError`. However, this check is only performed in between the processing of each object and the re-deferring only happens when the task is within `_buffer_time` seconds of hitting the deadline. So if the processing of an individual model instance takes more than `_buffer_time` seconds then the `DeadlineExceededError` may still be hit, which will cause that task to be retried from the beginning, thus re-processing some of the model instances.

If `_buffer_time` is None (default) then the buffer time will be dynamically calculated from the longest iteration time.

If `args` is specified, these arguments are passed as positional arguments to both `callback` (after the instance) and `finalize`.

`_shards` is the number of shards to use for processing. If `_delete_marker` is `True` then the Datastore entity that
tracks complete shards is deleted. If you want to keep these (as a log of sorts) then set this to `False`.

`_transactional` and `_queue` work in the same way as `defer()`

## Identifying a task shard

From a shard callback, you can identify the current shard by accessing `os.environ["DEFERRED_ITERATION_SHARD_INDEX"]` there is a constant defined for this key:

```
from djangae.deferred import DEFERRED_ITERATION_SHARD_INDEX_KEY
shard_index = int(os.environ[DEFERRED_ITERATION_SHARD_INDEX_KEY])
```

