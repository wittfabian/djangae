# encoding: utf-8

from django.db import models
from djangae.test import TestCase
from djangae.fields import CharField, ComputedCollationField


class CCollationModel(models.Model):
    field1 = CharField()
    field1_order = ComputedCollationField('field1')


class ComputedCollationFieldTests(TestCase):

    def test_basic_usage(self):
        instance1 = CCollationModel.objects.create(field1="Đavid")
        instance2 = CCollationModel.objects.create(field1="Łukasz")
        instance3 = CCollationModel.objects.create(field1="Ăna")
        instance4 = CCollationModel.objects.create(field1="Vera")

        results = CCollationModel.objects.order_by("field1_order")

        self.assertEqual(results[0], instance3)
        self.assertEqual(results[1], instance1)
        self.assertEqual(results[2], instance2)
        self.assertEqual(results[3], instance4)
    
