# Deferred

# djangae.deferred.defer

The App Engine SDK provides a utility function called `defer()` which is used to call
functions and methods from the task queue.

The built-in `defer()` method suffers from a number of issues with both bugs, and the API itself.

`djangae.deferred.defer` is a near-drop-in replacement for `google.appengine.ext.deferred.defer` with a few differences:

 - The code has been altered to always use a Datastore entity group unless the task is explicitly marked as being "small" (less than 100k) with the `_small_task=True` flag.
 - Transactional defers are always transactional, even if the task is > 100k (this is a bug in the original defer)
 - If a Django instance is passed as an argument to the called function, then the foreign key caches are wiped before
   deferring to avoid bloating and stale data when the task runs. This can be disabled with `_wipe_related_caches=False`

Everything else should behave in the same way. The actual running of deferred tasks still uses the Google handler (which is wrapped by Djangae)

