import os
from django.db import models

from djangae.deferred import defer_iteration_with_finalize, DEFERRED_ITERATION_SHARD_INDEX_KEY
from djangae.test import TestCase


_SHARD_COUNT = 5


class DeferIterationTestModel(models.Model):
    touched = models.BooleanField(default=False)
    finalized = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)


class DeferIterationTestSQLModel(models.Model):
    test_database = 'sql'

    touched = models.BooleanField(default=False)
    finalized = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)


def callback(instance, touch=True):
    shard_index = int(os.environ[DEFERRED_ITERATION_SHARD_INDEX_KEY])

    assert(shard_index >= 0)
    assert(shard_index < 5)

    if touch:
        instance.touched = True
    instance.save()


sporadic_error_counter = 0


def sporadic_error(instance):
    global sporadic_error_counter

    if instance.pk == 1:
        sporadic_error_counter += 1
        if sporadic_error_counter in (0, 1, 2):
            raise ValueError("Boom!")

    instance.touched = True
    instance.save()


def finalize(touch=True):
    for instance in DeferIterationTestModel.objects.all():
        instance.finalized = True
        instance.save()


def finalize_sql(touch=True):
    for instance in DeferIterationTestSQLModel.objects.all():
        instance.finalized = True
        instance.save()


class DeferDatastoreIterationTestCase(TestCase):
    def test_passing_args_and_kwargs(self):
        [DeferIterationTestModel.objects.create() for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.all(),
            callback,
            finalize,
            touch=False,  # kwarg to not touch the objects at all
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(0, DeferIterationTestModel.objects.filter(touched=True).count())

    def test_instances_hit(self):
        [DeferIterationTestModel.objects.create() for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.all(),
            callback,
            finalize,
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(25, DeferIterationTestModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestModel.objects.filter(finalized=True).count())

    def test_excluded_missed(self):
        [DeferIterationTestModel.objects.create(ignored=(i < 5)) for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.filter(ignored=False),
            callback,
            finalize,
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(5, DeferIterationTestModel.objects.filter(ignored=True).count())
        self.assertEqual(20, DeferIterationTestModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestModel.objects.filter(finalized=True).count())

    def test_shard_continue_on_error(self):
        [DeferIterationTestModel.objects.create(pk=i + 1) for i in range(25)]

        global sporadic_error_counter
        sporadic_error_counter = 0

        defer_iteration_with_finalize(
            DeferIterationTestModel.objects.all(),
            sporadic_error,
            finalize,
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(25, DeferIterationTestModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestModel.objects.filter(finalized=True).count())


class DeferSQLIterationTestCase(TestCase):

    def test_instances_hit(self):
        [DeferIterationTestSQLModel.objects.create() for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestSQLModel.objects.all(),
            callback,
            finalize_sql,
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(25, DeferIterationTestSQLModel.objects.filter(touched=True).count())
        self.assertEqual(25, DeferIterationTestSQLModel.objects.filter(finalized=True).count())

    def test_excluded_missed(self):
        [DeferIterationTestSQLModel.objects.create(ignored=(i < 5)) for i in range(25)]

        defer_iteration_with_finalize(
            DeferIterationTestSQLModel.objects.filter(ignored=False),
            callback,
            finalize_sql,
            _shards=_SHARD_COUNT
        )

        self.process_task_queues()

        self.assertEqual(5, DeferIterationTestSQLModel.objects.filter(ignored=True).count())
        self.assertEqual(20, DeferIterationTestSQLModel.objects.filter(touched=True).count())
