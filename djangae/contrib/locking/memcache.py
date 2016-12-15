import time
from django.core.cache import cache

from .kinds import LOCK_KINDS


class MemcacheLock(object):
    def __init__(self, identifier):
        self.identifier = identifier

    @classmethod
    def acquire(cls, identifier, wait=True, steal_after_ms=None, kind=LOCK_KINDS.WEAK):
        # Slightly misusing steal_after_ms here as it's actually used as the expiry time
        # for when the lock is set.
        acquired = cache.add(identifier, 1, steal_after_ms)
        if acquired:
            return cls(identifier)
        else:
            while wait and not acquired:
                time.sleep(0.1)
                acquired = cache.add(identifier, 1, steal_after_ms)

    def release(self):
        cache.delete(self.identifier)
