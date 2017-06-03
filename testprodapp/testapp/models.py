import uuid

from django.db import models


class UuidManager(models.Manager):

    def create_entities(self, count=1000):
        entities = []
        for i in range(count):
            entity = Uuid.objects.create()
            entities.append(entity.value)
        return str(sorted(entities)[count/2])


class Uuid(models.Model):
    value = models.CharField(max_length=36, default=uuid.uuid4)

    objects = UuidManager()
