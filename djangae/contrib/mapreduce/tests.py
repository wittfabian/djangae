import logging

from django.db import models
from djangae.test import TestCase
from djangae.test import process_task_queues, _get_queued_tasks, process_task, process_pipelines
import webapp2
import pipeline

from mapreduce.mapper_pipeline import MapperPipeline
from mapreduce.mapreduce_pipeline import MapreducePipeline
# from mapreduce import mapreduce_pipeline


class TestNode(models.Model):
    data = models.CharField(max_length=32)
    counter = models.IntegerField()


class MapreduceTestCase(TestCase):

    def setUp(self):
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


def letter_count_map(data):
    """Word Count map function."""
    letters = [x for x in data]
    logging.debug("Got %s", letters)
    for l in letters:
        yield (l, "")

def word_count_reduce(key, values):
    """Word Count reduce function."""
    yield "%s: %d\n" % (key, len(values))
