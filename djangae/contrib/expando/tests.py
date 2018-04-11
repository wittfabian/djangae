
from django.db import connection, models
from google.appengine.api.datastore import Get, Key

from djangae.contrib.expando import E, ExpandoModel
from djangae.test import TestCase


class ExpandoTestModel(ExpandoModel):
    pass


class ExpandoTests(TestCase):

    def test_creating_expando_fields(self):
        # Expando fields have to be explicitly registered by passing the values as E objects
        instance1 = ExpandoTestModel(field1=E(1), field2=E("two"))
        instance2 = ExpandoTestModel(field1=E("bananas"), field2=E(999), field3=E("cheese"))

        # Expando fields appear in the fields for the instance meta (but not the class meta)
        field1 = instance1._meta.get_field("field1")
        field2 = instance1._meta.get_field("field2")

        self.assertEqual(field1.__class__, models.IntegerField)
        self.assertEqual(field2.__class__, models.CharField)

        field1 = instance2._meta.get_field("field1")
        field2 = instance2._meta.get_field("field2")

        self.assertEqual(field1.__class__, models.CharField)
        self.assertEqual(field2.__class__, models.IntegerField)

        # Instance._meta also gains an expando_fields property so we can see what additional
        # fields the instance has beyond the class
        self.assertItemsEqual(instance1._meta.expando_fields, ["field1", "field2"])
        self.assertItemsEqual(instance2._meta.expando_fields, ["field1", "field2", "field3"])

        instance1.save()
        instance2.save()

        ns = connection.settings_dict.get("NAMESPACE", "")

        # Saving the expando should set the right stuff in the datastore
        entity1 = Get(
            Key.from_path(ExpandoTestModel._meta.db_table, instance1.pk, namespace=ns)
        )

        entity2 = Get(
            Key.from_path(ExpandoTestModel._meta.db_table, instance2.pk, namespace=ns)
        )

        self.assertEqual(entity1["field1"], 1)
        self.assertEqual(entity1["field2"], "two")

        self.assertEqual(entity2["field1"], "bananas")
        self.assertEqual(entity2["field2"], 999)

        # When querying you must pass values as E objects to avoid Django complaining that
        # they aren't real fields.
        self.assertTrue(ExpandoTestModel.objects.filter(field1=E(1)).exists())
        self.assertTrue(ExpandoTestModel.objects.filter(field1=E("bananas")).exists())

        # Reloading the instance should automatically generate the expando fields
        instance1 = ExpandoTestModel.objects.get(pk=instance1.pk)
        self.assertEqual(instance1._meta.expando_fields, ["field1", "field2"])
        self.assertEqual(instance1.field1, 1)
        self.assertEqual(instance1.field2, "two")
