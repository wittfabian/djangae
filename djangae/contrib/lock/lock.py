from .models import Lock


class LockAcquisitionError(Exception):
    pass


class LocknessMonster(object):
    """ Function decorator and context manager for locking a function or block of code so that only
        1 thread can excecute it at any given time.
        `identifier` should be a string which uniquely identifies the block of code that you want
        to lock.
        If `wait` is False and another thread is already running then:
            If used as a decorator, the function will not be run.
            If used as a context manager, LockAcquisitionError will be raised when entering `with`.
        If `steal_after_ms` is passed then existing locks on this function which are older
        than this value will be ignored.
    """

    def __init__(self, identifier, wait=True, steal_after_ms=None):
        self.identifier = identifier
        self.wait = wait
        self.steal_after_ms = steal_after_ms

    def __call__(self, function):
        self.decorated_function = function
        return self._replacement_function

    def _replacement_function(self, *args, **kwargs):
        try:
            with self:
                return self.decorated_function(*args, **kwargs)
        except LockAcquisitionError:
            # In the case where self.wait is False and the Lock is already in use self.__enter__
            # will raise this exception
            return  # Do not run the function

    def __enter__(self):
        self.lock = Lock.objects.acquire(self.identifier, self.wait, self.steal_after_ms)
        if self.lock is None:
            raise LockAcquisitionError("Failed to acquire lock for '%s'" % self.identifier)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.lock:
            self.lock.release()
            self.lock = None  # Just for neatness


lock = LocknessMonster
