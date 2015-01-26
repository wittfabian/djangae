from django.db import models
from django.test import TestCase

from .models import UniqueAction, encode_model
from djangae.test import process_task_queues
from djangae.db.constraints import UniquenessMixin


class TestModel(UniquenessMixin, models.Model):
    name = models.CharField(max_length=32, unique=True)
    counter1 = models.IntegerField()
    counter2 = models.IntegerField()

    class Meta:
        unique_together = [('counter1', 'counter2')]


class MapperTests(TestCase):

    def setUp(self):
        TestModel.objects.create(name="name1", counter1=1, counter2=1)
        TestModel.objects.create(name="name3", counter1=1, counter2=2)

    def test_check_ok(self):
        # A check should produce no errors.
        UniqueAction.objects.create(action_type="check", model=encode_model(TestModel))
        process_task_queues()

        a = UniqueAction.objects.get()
        self.assertEqual(a.status, "done")
        self.assertEqual(0, a.actionlog_set.count())

