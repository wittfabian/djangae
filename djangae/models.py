from django.db import models

from djangae import patches  # noqa


class CounterShard(models.Model):
    count = models.PositiveIntegerField()
    label = models.CharField(max_length=500)

    class Meta:
        app_label = "djangae"


class DeferIterationMarker(models.Model):
    """
        Marker to keep track of sharded defer
        iteration tasks
    """

    # Set to True when all shards have been deferred
    is_ready = models.BooleanField(default=False)

    shard_count = models.PositiveIntegerField(default=0)
    shards_complete = models.PositiveIntegerField(default=0)

    delete_on_completion = models.BooleanField(default=True)

    class Meta:
        app_label = "djangae"

    @property
    def is_finished(self):
        return self.is_ready and self.shard_count == self.shards_complete
