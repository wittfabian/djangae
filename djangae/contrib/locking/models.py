# STANDARD LIB
from datetime import timedelta
import time

# THRID PARTY
from django.db import models
from django.utils import timezone

# DJANGAE
from djangae.db import transaction
from djangae.fields import CharField


class LockQuerySet(models.query.QuerySet):

    def acquire(self, identifier, wait=True, steal_after_ms=None):
        """ Create or fetch the Lock with the given `identifier`.
        `wait`:
            If True, wait until the Lock is available, otherwise if the lcok is not available then
            return None.
        `steal_after_ms`:
            If the lock is not available (already exists), then steal it if it's older than this.
            E.g. if you know that the section of code you're locking should never take more than
            3 seconds, then set this to 3000.
        """
        @transaction.atomic()
        def trans():
            lock = self.filter(identifier=identifier).first()
            if lock:
                # Lock already exists, so check if it's old enough to ignore/steal
                if (
                    steal_after_ms and
                    timezone.now() - lock.timestamp > timedelta(microseconds=steal_after_ms * 1000)
                ):
                    # We can steal it.  Update timestamp to now and return it
                    lock.timestamp = timezone.now()
                    lock.save()
                    return lock
            else:
                return DatastoreLock.objects.create(identifier=identifier)

        lock = trans()
        while wait and lock is None:
            time.sleep(0.1)  # Sleep for a bit between retries
            lock = trans()
        return lock


class DatastoreLock(models.Model):
    """ A marker for locking a block of code. """

    objects = LockQuerySet.as_manager()

    identifier = CharField(primary_key=True)
    timestamp = models.DateTimeField(default=timezone.now)

    def release(self):
        self.delete()
