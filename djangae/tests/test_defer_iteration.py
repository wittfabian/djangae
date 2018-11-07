from django.db import models

from djangae.deferred import defer_iteration_with_finalize
from djangae.test import TestCase


class DeferIterationTestModel(models.Model):
    touched = models.BooleanField(default=False)
    finalized = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)


def callback(instance):
    instance.touched = True
    instance.save()


def finalize():
    for instance in DeferIterationTestModel.objects.all():
        instance.finalized = True
        instance.save()


class DeferIterationTestCase(TestCase):
    def test_instances_hit(self):
        [DeferIterationTestModel.objects.create() for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.all(),
            callback,
            finalize
        )

        self.process_task_queues()

        self.assertEqual(25, DeferIterationTestModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestModel.objects.filter(finalized=True).count())

    def test_excluded_missed(self):
        [DeferIterationTestModel.objects.create(ignored=(i < 5)) for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.filter(ignored=False),
            callback,
            finalize
        )

        self.process_task_queues()

        self.assertEqual(5, DeferIterationTestModel.objects.filter(ignored=True).count())
        self.assertEqual(20, DeferIterationTestModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestModel.objects.filter(finalized=True).count())

