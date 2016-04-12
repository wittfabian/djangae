from django.db import models
from djangae.test import TestCase

from djangae.contrib.processing.mapreduce import (
    map_queryset,
    map_entities
)

from google.appengine.api import datastore

class TestModel(models.Model):
    class Meta:
        app_label = "mapreduce"

    is_true = models.BooleanField(default=False)


class Counter(models.Model):
    count = models.PositiveIntegerField(default=0)


def count(instance, counter_id):
    counter = Counter.objects.get(pk=counter_id)
    counter.count = models.F('count') + 1
    counter.save()


def delete():
    TestModel.objects.all().delete()


class MapQuerysetTests(TestCase):
    def setUp(self):
        for i in xrange(5):
            TestModel.objects.create(id=i+1)

    def test_filtering(self):
        counter = Counter.objects.create()
        map_queryset(
            TestModel.objects.filter(is_true=True),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )
        counter = Counter.objects.create()
        self.process_task_queues()
        counter.refresh_from_db()
        self.assertEqual(0, counter.count)

    def test_mapping_over_queryset(self):
        counter = Counter.objects.create()

        map_queryset(
            TestModel.objects.all(),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        counter.refresh_from_db()

        self.assertEqual(5, counter.count)
        self.assertFalse(TestModel.objects.count())

    def test_filters_apply(self):
        counter = Counter.objects.create()

        map_queryset(
            TestModel.objects.filter(pk__gt=2),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        counter.refresh_from_db()

        self.assertEqual(3, counter.count)
        self.assertFalse(TestModel.objects.count())


def count_entity(entity, counter_id):
    assert isinstance(entity, datastore.Entity)

    counter = Counter.objects.get(pk=counter_id)
    counter.count = models.F('count') + 1
    counter.save()


class MapEntitiesTests(TestCase):
    def setUp(self):
        for i in xrange(5):
            TestModel.objects.create(id=i+1)

    def test_mapping_over_entities(self):
        counter = Counter.objects.create()

        map_entities(
            TestModel._meta.db_table,
            count_entity,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        counter.refresh_from_db()

        self.assertEqual(5, counter.count)
        self.assertFalse(TestModel.objects.count())
