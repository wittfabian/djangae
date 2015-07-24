from django.db.models.sql.datastructures import EmptyResultSet
from django.db import models, connections
from djangae.test import TestCase
from djangae.db.backends.appengine.query import transform_query, Query, WhereNode
from django.db.models.query import Q

class TransformTestModel(models.Model):
    field1 = models.CharField(max_length=255)
    field2 = models.CharField(max_length=255, unique=True)
    field3 = models.CharField(null=True, max_length=255)


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

    def test_ordering(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.filter(field1="One", field2="Two").order_by("field1", "-field2").query
        )

        self.assertEqual(query.model, TransformTestModel)
        self.assertEqual(query.kind, 'SELECT')
        self.assertEqual(query.tables, [ TransformTestModel._meta.db_table ])
        self.assertTrue(query.where)
        self.assertEqual(2, len(query.where.children)) # Two child nodes
        self.assertEqual(["field1", "-field2"], query.order_by)

    def test_projection(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.only("field1").query
        )

        self.assertItemsEqual(["id", "field1"], query.columns)

        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.values_list("field1").query
        )

        self.assertEqual(["field1"], query.columns)

        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.defer("field1").query
        )

        self.assertItemsEqual(["id", "field2", "field3"], query.columns)

    def test_no_results_returns_emptyresultset(self):
        self.assertRaises(
            EmptyResultSet,
            transform_query,
            connections['default'],
            "SELECT",
            TransformTestModel.objects.none().query
        )

    def test_offset_and_limit(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.all()[5:10].query
        )

        self.assertEqual(5, query.offset)
        self.assertEqual(5, query.limit)

    def test_isnull(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.filter(field3__isnull=True).all()[5:10].query
        )

        self.assertIsNone(query.where.children[0].value)
        self.assertEqual("=", query.where.children[0].operator)

    def test_distinct(self):
        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.distinct("field2", "field3").query
        )

        self.assertTrue(query.distinct)
        self.assertEqual(query.columns, ["field2", "field3"])

        query = transform_query(
            connections['default'],
            "SELECT",
            TransformTestModel.objects.distinct().values("field2", "field3").query
        )

        self.assertTrue(query.distinct)
        self.assertEqual(query.columns, ["field2", "field3"])

from djangae.tests.test_connector import TestUser, Relation
from djangae.db.backends.appengine.dnf import normalize_query

class QueryNormalizationTests(TestCase):
    """
        The parse_dnf function takes a Django where tree, and converts it
        into a tree of one of the following forms:

        [ (column, operator, value), (column, operator, value) ] <- AND only query
        [ [(column, operator, value)], [(column, operator, value) ]] <- OR query, of multiple ANDs
    """

    def test_and_with_child_or_promoted(self):
        """
            Given the following tree:

                   AND
                  / | \
                 A  B OR
                      / \
                     C   D

             The OR should be promoted, so the resulting tree is

                      OR
                     /   \
                   AND   AND
                  / | \ / | \
                 A  B C A B D
        """


        query = Query(TestUser, "SELECT")
        query.where = WhereNode()
        query.where.children.append(WhereNode())
        query.where.children[-1].column = "A"
        query.where.children[-1].operator = "="
        query.where.children.append(WhereNode())
        query.where.children[-1].column = "B"
        query.where.children[-1].operator = "="
        query.where.children.append(WhereNode())
        query.where.children[-1].connector = "OR"
        query.where.children[-1].children.append(WhereNode())
        query.where.children[-1].children[-1].column = "C"
        query.where.children[-1].children[-1].operator = "="
        query.where.children[-1].children.append(WhereNode())
        query.where.children[-1].children[-1].column = "D"
        query.where.children[-1].children[-1].operator = "="

        query = normalize_query(query)

        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(2, len(query.where.children))
        self.assertFalse(query.where.children[0].is_leaf)
        self.assertFalse(query.where.children[1].is_leaf)
        self.assertEqual(query.where.children[0].connector, "AND")
        self.assertEqual(query.where.children[1].connector, "AND")
        self.assertEqual(3, len(query.where.children[0].children))
        self.assertEqual(3, len(query.where.children[1].children))

    def test_and_queries(self):
        qs = TestUser.objects.filter(username="test").all()

        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))

        self.assertTrue(1, len(query.where.children))
        self.assertEqual(query.where.children[0].children[0].column, "username")
        self.assertEqual(query.where.children[0].children[0].operator, "=")
        self.assertEqual(query.where.children[0].children[0].value, "test")

        qs = TestUser.objects.filter(username="test", email="test@example.com")

        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))

        self.assertTrue(2, len(query.where.children[0].children))
        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(query.where.children[0].connector, "AND")
        self.assertEqual(query.where.children[0].children[0].column, "username")
        self.assertEqual(query.where.children[0].children[0].operator, "=")
        self.assertEqual(query.where.children[0].children[0].value, "test")
        self.assertEqual(query.where.children[0].children[1].column, "email")
        self.assertEqual(query.where.children[0].children[1].operator, "=")
        self.assertEqual(query.where.children[0].children[1].value, "test@example.com")

        qs = TestUser.objects.filter(username="test").exclude(email="test@example.com")
        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))


        self.assertTrue(2, len(query.where.children[0].children))
        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(query.where.children[0].connector, "AND")
        self.assertEqual(query.where.children[0].children[0].column, "username")
        self.assertEqual(query.where.children[0].children[0].operator, "=")
        self.assertEqual(query.where.children[0].children[0].value, "test")
        self.assertEqual(query.where.children[0].children[1].column, "email")
        self.assertEqual(query.where.children[0].children[1].operator, "<")
        self.assertEqual(query.where.children[0].children[1].value, "test@example.com")
        self.assertEqual(query.where.children[1].children[0].column, "username")
        self.assertEqual(query.where.children[1].children[0].operator, "=")
        self.assertEqual(query.where.children[1].children[0].value, "test")
        self.assertEqual(query.where.children[1].children[1].column, "email")
        self.assertEqual(query.where.children[1].children[1].operator, ">")
        self.assertEqual(query.where.children[1].children[1].value, "test@example.com")


        instance = Relation(pk=1)
        qs = instance.related_set.filter(headline__startswith='Fir')

        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))

        self.assertTrue(2, len(query.where.children[0].children))
        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(query.where.children[0].connector, "AND")
        self.assertEqual(query.where.children[0].children[0].column, "relation_id")
        self.assertEqual(query.where.children[0].children[0].operator, "=")
        self.assertEqual(query.where.children[0].children[0].value, 1)
        self.assertEqual(query.where.children[0].children[1].column, "_idx_startswith_headline")
        self.assertEqual(query.where.children[0].children[1].operator, "=")
        self.assertEqual(query.where.children[0].children[1].value, u"Fir")


    def test_or_queries(self):
        qs = TestUser.objects.filter(
            username="python").filter(
            Q(username__in=["ruby", "jruby"]) | (Q(username="php") & ~Q(username="perl"))
        )

        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))

        # After IN and != explosion, we have...
        # (AND: (username='python', OR: (username='ruby', username='jruby', AND: (username='php', AND: (username < 'perl', username > 'perl')))))

        # Working backwards,
        # AND: (username < 'perl', username > 'perl') can't be simplified
        # AND: (username='php', AND: (username < 'perl', username > 'perl')) can become (OR: (AND: username = 'php', username < 'perl'), (AND: username='php', username > 'perl'))
        # OR: (username='ruby', username='jruby', (OR: (AND: username = 'php', username < 'perl'), (AND: username='php', username > 'perl')) can't be simplified
        # (AND: (username='python', OR: (username='ruby', username='jruby', (OR: (AND: username = 'php', username < 'perl'), (AND: username='php', username > 'perl'))
        # becomes...
        # (OR: (AND: username='python', username = 'ruby'), (AND: username='python', username='jruby'), (AND: username='python', username='php', username < 'perl') \
        #      (AND: username='python', username='php', username > 'perl')

        self.assertTrue(4, len(query.where.children[0].children))

        self.assertEqual(query.where.children[0].connector, "AND")
        self.assertEqual(query.where.children[0].children[0].column, "username")
        self.assertEqual(query.where.children[0].children[0].operator, "=")
        self.assertEqual(query.where.children[0].children[0].value, "python")
        self.assertEqual(query.where.children[0].children[1].column, "username")
        self.assertEqual(query.where.children[0].children[1].operator, "=")
        self.assertEqual(query.where.children[0].children[1].value, "php")
        self.assertEqual(query.where.children[0].children[2].column, "username")
        self.assertEqual(query.where.children[0].children[2].operator, "<")
        self.assertEqual(query.where.children[0].children[2].value, "perl")

        self.assertEqual(query.where.children[1].connector, "AND")
        self.assertEqual(query.where.children[1].children[0].column, "username")
        self.assertEqual(query.where.children[1].children[0].operator, "=")
        self.assertEqual(query.where.children[1].children[0].value, "python")
        self.assertEqual(query.where.children[1].children[1].column, "username")
        self.assertEqual(query.where.children[1].children[1].operator, "=")
        self.assertEqual(query.where.children[1].children[1].value, "jruby")

        self.assertEqual(query.where.children[2].connector, "AND")
        self.assertEqual(query.where.children[2].children[0].column, "username")
        self.assertEqual(query.where.children[2].children[0].operator, "=")
        self.assertEqual(query.where.children[2].children[0].value, "python")
        self.assertEqual(query.where.children[2].children[1].column, "username")
        self.assertEqual(query.where.children[2].children[1].operator, "=")
        self.assertEqual(query.where.children[2].children[1].value, "php")
        self.assertEqual(query.where.children[2].children[2].column, "username")
        self.assertEqual(query.where.children[2].children[2].operator, ">")
        self.assertEqual(query.where.children[2].children[2].value, "perl")

        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(query.where.children[3].connector, "AND")
        self.assertEqual(query.where.children[3].children[0].column, "username")
        self.assertEqual(query.where.children[3].children[0].operator, "=")
        self.assertEqual(query.where.children[3].children[0].value, "python")
        self.assertEqual(query.where.children[3].children[1].column, "username")
        self.assertEqual(query.where.children[3].children[1].operator, "=")
        self.assertEqual(query.where.children[3].children[1].value, "ruby")

        qs = TestUser.objects.filter(username="test") | TestUser.objects.filter(username="cheese")

        query = normalize_query(transform_query(
            connections['default'],
            "SELECT", qs.query
        ))

        self.assertEqual(query.where.connector, "OR")
        self.assertEqual(2, len(query.where.children))
        self.assertTrue(query.where.children[0].is_leaf)
        self.assertEqual("cheese", query.where.children[0].value)
        self.assertTrue(query.where.children[1].is_leaf)
        self.assertEqual("test", query.where.children[1].value)


        qs = TestUser.objects.using("default").filter(username__in=set()).values_list('email')

        with self.assertRaises(EmptyResultSet):
            query = normalize_query(transform_query(
                connections['default'],
                "SELECT", qs.query
            ))

        return

        qs = TestUser.objects.filter(username__startswith='Hello') |  TestUser.objects.filter(username__startswith='Goodbye')
        expected = ('OR', [
            ('LIT', ('_idx_startswith_username', '=', u'Hello')),
            ('LIT', ('_idx_startswith_username', '=', u'Goodbye'))
        ])
        self.assertEqual(expected, parse_dnf(qs.query.where, connection=connection)[0])

        qs = TestUser.objects.filter(pk__in=[1, 2, 3])

        expected = ('OR', [
            ('LIT', ("id", "=", datastore.Key.from_path(TestUser._meta.db_table, 1))),
            ('LIT', ("id", "=", datastore.Key.from_path(TestUser._meta.db_table, 2))),
            ('LIT', ("id", "=", datastore.Key.from_path(TestUser._meta.db_table, 3))),
        ])

        self.assertEqual(expected, parse_dnf(qs.query.where, connection=connection)[0])

        qs = TestUser.objects.filter(pk__in=[1, 2, 3]).filter(username="test")

        expected = ('OR', [
            ('AND', [
                ('LIT', (u'id', '=', datastore.Key.from_path(TestUser._meta.db_table, 1))),
                ('LIT', ('username', '=', 'test'))
            ]),
            ('AND', [
                ('LIT', (u'id', '=', datastore.Key.from_path(TestUser._meta.db_table, 2))),
                ('LIT', ('username', '=', 'test'))
            ]),
            ('AND', [
                ('LIT', (u'id', '=', datastore.Key.from_path(TestUser._meta.db_table, 3))),
                ('LIT', ('username', '=', 'test'))
            ])
        ])
        self.assertEqual(expected, parse_dnf(qs.query.where, connection=connection)[0])
