from django.db import models, connections
from djangae.test import TestCase
from djangae.db.backends.appengine.query import transform_query


class TransformTestModel(models.Model):
    field1 = models.CharField(max_length=255)
    field2 = models.CharField(max_length=255, unique=True)


class TransformQueryTest(TestCase):

    def test_basic_query(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.all().query
        )

        self.assertEqual(query.model, TransformTestModel)
        self.assertEqual(query.kind, 'SELECT')
        self.assertEqual(query.tables, [ TransformTestModel._meta.db_table ])
        self.assertIsNone(query.where)


    def test_and_filter(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.filter(field1="One", field2="Two").all().query
        )

        self.assertEqual(query.model, TransformTestModel)
        self.assertEqual(query.kind, 'SELECT')
        self.assertEqual(query.tables, [ TransformTestModel._meta.db_table ])
        self.assertTrue(query.where)
        self.assertEqual(2, len(query.where.children)) # Two child nodes

    def test_exclude_filter(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.exclude(field1="One").all().query
        )

        self.assertEqual(query.model, TransformTestModel)
        self.assertEqual(query.kind, 'SELECT')
        self.assertEqual(query.tables, [ TransformTestModel._meta.db_table ])
        self.assertTrue(query.where)
        self.assertEqual(1, len(query.where.children)) # One child node
        self.assertTrue(query.where.children[0].negated)
        self.assertEqual(1, len(query.where.children[0].children))
