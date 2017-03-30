"""
    Tests for "special indexing" (E.g. __contains, __startswith etc.)
"""
from djangae.test import TestCase

from django.core.management import call_command
from django.db import connection
from django.db import models


class ContainsModel(models.Model):
    field1 = models.CharField(max_length=500)


class ContainsIndexerTests(TestCase):

    def _list_contains_model_tables(self):
        with connection.cursor() as cursor:
            return [
                x for x in connection.introspection.table_names(cursor)
                if ContainsModel._meta.db_table in x
            ]

    def test_basic_usage(self):
        c1 = ContainsModel.objects.create(field1="Adam")
        c2 = ContainsModel.objects.create(field1="Luke")

        self.assertEqual(ContainsModel.objects.filter(field1__contains="Ad").first(), c1)
        self.assertEqual(ContainsModel.objects.filter(field1__contains="Lu").first(), c2)

    def test_flush_wipes_descendent_kinds(self):
        """
            The contains index generates a kind for each model field which
            uses a __contains index. When we flush the database these kinds should also
            be wiped if their "parent" model table is wiped
        """

        ContainsModel.objects.create(field1="Vera")

        table_names = self._list_contains_model_tables()

        self.assertItemsEqual([
            ContainsModel._meta.db_table,
            "djangae_idx_{}_field1".format(ContainsModel._meta.db_table)
        ], table_names)

        # Flush the database
        call_command('flush', interactive=False, load_initial_data=False)

        # Should be zero tables!
        self.assertFalse(self._list_contains_model_tables(), self._list_contains_model_tables())

    def test_delete_wipes_descendent_index_tables(self):
        c1 = ContainsModel.objects.create(field1="Phil")
        c1.delete()
        self.assertFalse(self._list_contains_model_tables(), self._list_contains_model_tables())
