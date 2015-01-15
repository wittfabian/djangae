import logging

from django.test import TestCase, RequestFactory
from django.db import models

from djangae.contrib.mappers.queryset import QueryDef
from djangae.test import process_task_queues
from djangae.contrib.mappers.pipes import MapReduceTask

class TestNode(models.Model):
    data = models.CharField(max_length=32)
    counter = models.IntegerField()


class TestMapperClass(MapReduceTask):

    model = TestNode
    name = 'test_map'

    @staticmethod
    def map(entity):
        if entity.counter % 2:
            entity.delete()
            yield ('removed', [entity.pk])
        else:
            yield ('remains', [entity.pk])

class TestMapperClass2(MapReduceTask):

    model = TestNode
    name = 'test_map_2'

    @staticmethod
    def map(entity):
        entity.data = "hit"
        entity.save()


class MapReduceTestCase(TestCase):

    def setUp(self):
        for x in xrange(100):
            TestNode(data="TestNode{0}".format(x), counter=x).save()

    def test_all_models_delete(self):
        self.assertEqual(TestNode.objects.count(), 100)
        TestMapperClass().start()
        process_task_queues()
        self.assertEqual(TestNode.objects.count(), 50)

    def test_map_fruit_update(self):
        self.assertEqual(TestNode.objects.count(), 100)
        TestMapperClass2().start()
        process_task_queues()
        nodes = TestNode.objects.all()
        self.assertTrue(all(x.data == 'hit' for x in nodes))
