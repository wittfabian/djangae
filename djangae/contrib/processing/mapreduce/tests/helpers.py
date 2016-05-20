from mapreduce import output_writers
from django.db import models
from djangae.test import TestCase

from djangae.contrib.processing.mapreduce import (
    map_queryset,
    map_entities,
    map_reduce_queryset,
    map_reduce_entities,
    get_pipeline_by_id,
)

from google.appengine.api import datastore

class TestModel(models.Model):
    class Meta:
        app_label = "mapreduce"

    is_true = models.BooleanField(default=False)
    text = models.CharField(null=True)


class Counter(models.Model):
    count = models.PositiveIntegerField(default=0)


def count(instance, counter_id):
    counter = Counter.objects.get(pk=counter_id)
    counter.count = models.F('count') + 1
    counter.save()


def yield_letters(instance):
    if hasattr(instance, 'text'):
        text = instance.text
    else:
        text = instance.get('text', '')
    for letter in text:
        yield (letter, "")


def reduce_count(key, values):
    yield (key, len(values))


def delete():
    TestModel.objects.all().delete()


class MapReduceEntityTests(TestCase):

    def setUp(self):
        for i in xrange(5):
            TestModel.objects.create(
                id=i+1,
                text="abcc"
            )

    def test_mapreduce_over_entities(self):
        pipeline = map_reduce_entities(
            TestModel._meta.db_table,
            yield_letters,
            reduce_count,
            output_writers.GoogleCloudStorageKeyValueOutputWriter,
            output_writer_kwargs={
                'bucket_name': 'test-bucket'
            }
        )
        self.process_task_queues()
        # Refetch the pipeline record
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)


class MapReduceQuerysetTests(TestCase):

    def setUp(self):
        for i in xrange(5):
            TestModel.objects.create(
                id=i+1,
                text="abcc"
            )

    def test_mapreduce_over_queryset(self):
        pipeline = map_reduce_queryset(
            TestModel.objects.all(),
            yield_letters,
            reduce_count,
            output_writers.GoogleCloudStorageKeyValueOutputWriter,
            output_writer_kwargs={
                'bucket_name': 'test-bucket'
            }
        )
        self.process_task_queues()
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)


class MapQuerysetTests(TestCase):
    def setUp(self):
        for i in xrange(5):
            TestModel.objects.create(id=i+1)

    def test_filtering(self):
        counter = Counter.objects.create()
        pipeline = map_queryset(
            TestModel.objects.filter(is_true=True),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )
        counter = Counter.objects.create()
        self.process_task_queues()
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)
        counter.refresh_from_db()
        self.assertEqual(0, counter.count)

    def test_mapping_over_queryset(self):
        counter = Counter.objects.create()

        pipeline = map_queryset(
            TestModel.objects.all(),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)
        counter.refresh_from_db()

        self.assertEqual(5, counter.count)
        self.assertFalse(TestModel.objects.count())

    def test_filters_apply(self):
        counter = Counter.objects.create()

        pipeline = map_queryset(
            TestModel.objects.filter(pk__gt=2),
            count,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)
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

        pipeline = map_entities(
            TestModel._meta.db_table,
            count_entity,
            finalize_func=delete,
            counter_id=counter.pk
        )

        self.process_task_queues()
        pipeline = get_pipeline_by_id(pipeline.pipeline_id)
        self.assertTrue(pipeline.has_finalized)
        counter.refresh_from_db()

        self.assertEqual(5, counter.count)
        self.assertFalse(TestModel.objects.count())
