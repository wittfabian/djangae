import logging

from django.db import models
from djangae.test import TestCase
from djangae.test import process_task_queues
import webapp2
from mapreduce.mapreduce_pipeline import MapreducePipeline


class TestNode(models.Model):
    data = models.CharField(max_length=32)
    counter = models.IntegerField()


class MapreduceTestCase(TestCase):

    def setUp(self):
        for x in range(20):
            self.testnode = TestNode()
            self.testnode.data = 'Lol'
            self.testnode.counter = 1
            self.testnode.save()
        super(MapreduceTestCase, self).setUp()


    def test_mapreduce(self):
        """
            Tests mapreduce
        """
        pipe = MapreducePipeline(
            "word_count",
            "djangae.contrib.mapreduce.tests.letter_count_map",
            "djangae.contrib.mapreduce.tests.word_count_reduce",
            "mapreduce.input_readers.RandomStringInputReader",
            "mapreduce.output_writers.GoogleCloudStorageOutputWriter",
            mapper_params={'count': 10},
            reducer_params={"mime_type": "text/plain", 'output_writer': {'bucket_name': 'test'}},
            shards=1
        )
        pipe.start()
        process_task_queues()

    def test_django_input(self):
        pipe = MapreducePipeline(
            "word_count",
            "djangae.contrib.mapreduce.tests.model_counter_increment",
            "djangae.contrib.mapreduce.tests.word_count_reduce",
            "djangae.contrib.mapreduce.input_readers.DjangoInputReader",
            "mapreduce.output_writers.GoogleCloudStorageOutputWriter",
            mapper_params={'count': 10, 'input_reader': {'model': 'mapreduce.TestNode'}},
            reducer_params={"mime_type": "text/plain", 'output_writer': {'bucket_name': 'test'}},
            shards=3
        )
        pipe.start()
        process_task_queues()


def letter_count_map(data):
    """Word Count map function."""
    letters = [x for x in data]
    logging.debug("Got %s", letters)
    for l in letters:
        yield (l, "")

def model_counter_increment(instance):
    """Word Count map function."""
    instance.counter += 1
    yield (instance.pk, "")

def word_count_reduce(key, values):
    """Word Count reduce function."""
    yield "%s: %d\n" % (key, len(values))
