from django.db import models

from djangae import patches


class CounterShard(models.Model):
    count = models.PositiveIntegerField()
    label = models.CharField(max_length=500)

# Apply our django patches
patches.patch()


# Make sure we clear the context cache properly
from djangae.db.backends.appengine.caching import reset_context
from django.core.signals import request_finished, request_started

request_finished.connect(reset_context, dispatch_uid="request_finished_context_reset")
request_started.connect(reset_context, dispatch_uid="request_started_context_reset")
