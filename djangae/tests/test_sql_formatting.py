from django.db import connections, models

from djangae.test import TestCase

from djangae.db.backends.appengine.formatting import generate_sql_representation
from djangae.db.backends.appengine.commands import SelectCommand


class FormattingTestModel(models.Model):
    field1 = models.IntegerField()
    field2 = models.CharField(max_length=10)
    field3 = models.TextField()


class SelectFormattingTest(TestCase):

    def test_select_star(self):
        command = SelectCommand(connections['default'], FormattingTestModel.objects.all().query)
        sql = generate_sql_representation(command)

        expected = """
SELECT (*) FROM {}
""".format(FormattingTestModel._meta.db_table).strip()

        self.assertEqual(expected, sql)

    def test_select_columns(self):
        command = SelectCommand(
            connections['default'],
            FormattingTestModel.objects.only("field1", "field2").all().query
        )
        sql = generate_sql_representation(command)

        expected = """
SELECT (field1, field2, id) FROM {}
""".format(FormattingTestModel._meta.db_table).strip()

        self.assertEqual(expected, sql)

    def test_select_in(self):
        """
            We don't build explicit IN queries, only multiple OR branches
            there is essentially no difference between the two
        """
        command = SelectCommand(
            connections['default'],
            FormattingTestModel.objects.filter(field1__in=[1, 2]).query
        )
        sql = generate_sql_representation(command)

        expected = """
SELECT (*) FROM {} WHERE (field1=2) OR (field1=1)
""".format(FormattingTestModel._meta.db_table).strip()

        self.assertEqual(expected, sql)

    def test_limit_applied(self):
        command = SelectCommand(
            connections['default'],
            FormattingTestModel.objects.all()[10:15].query
        )
        sql = generate_sql_representation(command)

        expected = """
SELECT (*) FROM {} OFFSET 10 LIMIT 5
""".format(FormattingTestModel._meta.db_table).strip()

        self.assertEqual(expected, sql)
    
