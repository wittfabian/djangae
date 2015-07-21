from django.db import models
from djangae.test import TestCase

from djangae.db.backends.appengine.query import transform_query


class TransformTestModel(models.Model):
    field1 = models.CharField(max_length=255)
    field2 = models.CharField(max_length=255, unique=True)


class TransformQueryTest(TestCase):

    def test_basic_query(self):
        query = transform_query("SELECT", TransformTestModel.objects.all().query)

        self.assertEqual(query.model, TransformTestModel)
        self.assertEqual(query.kind, 'SELECT')
        self.assertEqual(query.tables, [ TransformTestModel._meta.db_table ])
        self.assertIsNone(query.where)
