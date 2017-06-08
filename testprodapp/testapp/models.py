import uuid
import django
import djangae

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
        django_version = u".".join([str(x) for x in django.VERSION])
        djangae_version = djangae.VERSION

        result, _ = TestResult.objects.get_or_create(
            name=name,
            django_version=django_version,
            djangae_version=djangae_version
        )

        return result

    def set_result(self, name, status, score, data):
        result = TestResult.objects.get_result(name=name)
        result.status = status
        result.score = score
        result.data = data
        result.save()
        return result


class TestResult(models.Model):
    name = models.CharField(max_length=500, editable=False)
    django_version = models.CharField(max_length=10, editable=False)
    djangae_version = models.CharField(max_length=10, editable=False)

    class Meta:
        unique_together = [
            ("name", "django_version", "djangae_version")
        ]

    last_modified = models.DateField(auto_now=True, editable=False)
    status = models.CharField(
        max_length=50,
        choices=test_result_choices,
        default=test_result_choices[0][0],
        editable=False,
    )
    score = models.FloatField(default=-1, editable=False)
    data = JSONField(default=dict, editable=False)

    objects = TestResultManager()

    def __unicode__(self):
        return self.name


class UuidManager(models.Manager):

    def create_entities(self, count=100):
        entities = []

        batch_id = uuid.uuid4()

        for i in range(count):
            entity = Uuid.objects.create(batch_uuid=batch_id)
            entities.append(entity.value)

        return batch_id


class Uuid(models.Model):
    batch_uuid = models.UUIDField()
    value = models.CharField(max_length=32, default=uuid.uuid4)

    objects = UuidManager()
