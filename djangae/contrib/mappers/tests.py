import logging

from django.test import TestCase, RequestFactory
from django.db import models

from djangae.contrib.mappers.queryset import QueryDef
from djangae.test import process_task_queues
from djangae.contrib.mappers.pipes import MapReduceTask

class TestNode(models.Model):
    data = models.CharField(max_length=32)
    couter = models.IntegerField()


class TestFruit(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    color = models.CharField(max_length=32)


def test_mapper_delete_evens(entity):
    if entity.couter % 2 == 0:
        logging.info('---Deleteing---' + entity.counter)
        entity.delete()


class TestMapperClass(MapReduceTask):

    query_def = QueryDef('mappers.TestModel').all()
    name = 'test_map'

    @staticmethod
    def map(entity):
        logging.info("{0}============".format(entity))


class MapReduceTestCase(TestCase):

    def setUp(self):
        for x in xrange(100):
            TestNode(data="TestNode{0}".format(x), couter=x).save()

    def test_all_models_split(self):
        TestMapperClass().start()
        process_task_queues()
        self.assertEqual(TestNode.objects.count(), 50)
