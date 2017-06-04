import uuid

from django.db import models
from djangae.fields import JSONField

test_result_choices = [(x, x) for x in [
    'new',
    'running',
    'error',
    'success',
]]


class TestResultManager(models.Manager):

    def get_result(self, name):
        result, _ = TestResult.objects.get_or_create(name=name)
        return result

    def set_result(self, name, status, score, data):
        result = TestResult.objects.get_result(name=name)
        result.status = status
        result.score = score
        result.data = data
        result.save()
        return result


class TestResult(models.Model):

    last_modified = models.DateField(auto_now=True, editable=False)
    name = models.CharField(max_length=500, editable=False)
    status = models.CharField(
        max_length=50,
        choices=test_result_choices,
        default=test_result_choices[0][0],
        editable=False,
        )
    score = models.FloatField(default=-1, editable=False)
    data = JSONField(default=dict, editable=False)

    objects = TestResultManager()


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
