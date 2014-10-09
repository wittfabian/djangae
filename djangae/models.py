from django.db import models

class CounterShard(models.Model):
    count = models.PositiveIntegerField()
