# Environment

Djangae contains a small collection of utility functions which are useful on App Engine.

## Retry

This is a helper for calling functions which may intermittently throw errors.
It is useful for things such as performing Datastore transactions which may collide, or calling other APIs which may occasionally fail but that should succeed on a subsequent attempt.

### `djangae.utils.retry`

```python
retry(function, _catch=None, _retries=3, _initial_wait=375, _max_wait=30000)
```

Calls the given function, catching the given exception(s), and retrying up to a maximum of `_retries` times.
If the intial call fails, it will wait `_initial_wait` milliseconds before making the second attempt.
The wait will double on each subsequent retry, up to a maximum of `_max_wait` milliseconds.

Note that `_retries` is the maximum number of *re*tries.  So the maximum number of possible attempts is `_retries + 1`.

`_catch` defaults to:

```python
(
    djangae.db.transaction.TransactionFailedError,
	google.appengine.api.datastore_errors.Error,
	google.appengine.runtime.apiproxy_errors.Error
)
```

### `djangae.utils.retry_on_error`

A function decorator which routes the function through `retry`.

```python
@retry_on_error(_catch=None, _retries=3, _initial_wait=375, _max_wait=30000)
def my_function():
    ...
```

### `djangae.utils.retry_until_successful`

```pythonn
retry(function, _catch=None, _retries=∞, _initial_wait=375, _max_wait=30000)
```

The same as `retry`, but `_retries` is unlimited, so it will keep on retrying until either it succeeds or you hit an uncaught exception, such as the App Engine `DeadlineExceededError`.
