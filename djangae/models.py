from django.db import models

from djangae import patches


class CounterShard(models.Model):
    count = models.PositiveIntegerField()
    label = models.CharField(max_length=500)

# Apply our django patches
patches.patch()
