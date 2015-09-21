from collections import OrderedDict

# LIBRARIES
from django.db import models
from django.db.utils import IntegrityError
from django.contrib.contenttypes.models import ContentType

# DJANGAE
from djangae.db import transaction
from djangae.fields import (
    ComputedCharField,
    GenericRelationField,
    JSONField,
    ListField,
    RelatedSetField,
    RelatedListField,
    ShardedCounterField,
    SetField,
)
from djangae.fields.counting import DEFAULT_SHARD_COUNT
from djangae.models import CounterShard
from djangae.test import TestCase


class ComputedFieldModel(models.Model):
    def computer(self):
        return "%s_%s" % (self.int_field, self.char_field)

    int_field = models.IntegerField()
    char_field = models.CharField(max_length=50)
    test_field = ComputedCharField(computer, max_length=50)

    class Meta:
        app_label = "djangae"


class ComputedFieldTests(TestCase):
    def test_computed_field(self):
        instance = ComputedFieldModel(int_field=1, char_field="test")
        instance.save()
        self.assertEqual(instance.test_field, "1_test")

        # Try getting and saving the instance again
        instance = ComputedFieldModel.objects.get(test_field="1_test")
        instance.save()


class ModelWithCounter(models.Model):
    counter = ShardedCounterField()

    class Meta:
        app_label = "djangae"


class ModelWithManyCounters(models.Model):
    counter1 = ShardedCounterField()
    counter2 = ShardedCounterField()

    class Meta:
        app_label = "djangae"


class ModelWithCounterWithManyShards(models.Model):
    # The DEFAULT_SHARD_COUNT is based on the max allowed in a Datastore transaction
    counter = ShardedCounterField(shard_count=DEFAULT_SHARD_COUNT+5)

    class Meta:
        app_label = "djangae"


class ISOther(models.Model):
    name = models.CharField(max_length=500)

    def __unicode__(self):
        return "%s:%s" % (self.pk, self.name)

    class Meta:
        app_label = "djangae"


class RelationWithoutReverse(models.Model):
    name = models.CharField(max_length=500)

    class Meta:
        app_label = "djangae"


class RelationWithOverriddenDbTable(models.Model):
    class Meta:
        db_table = "bananarama"
        app_label = "djangae"


class GenericRelationModel(models.Model):
    relation_to_anything = GenericRelationField(null=True)
    unique_relation_to_anything = GenericRelationField(null=True, unique=True)

    class Meta:
        app_label = "djangae"


class ISModel(models.Model):
    related_things = RelatedSetField(ISOther)
    related_list = RelatedListField(ISOther, related_name="ismodel_list")
    limted_related = RelatedSetField(RelationWithoutReverse, limit_choices_to={'name': 'banana'}, related_name="+")
    children = RelatedSetField("self", related_name="+")

    class Meta:
        app_label = "djangae"


class IterableFieldModel(models.Model):
    set_field = SetField(models.CharField(max_length=1))
    list_field = ListField(models.CharField(max_length=1))

    class Meta:
        app_label = "djangae"


class JSONFieldModel(models.Model):
    json_field = JSONField(use_ordered_dict=True)


class ShardedCounterTest(TestCase):
    def test_basic_usage(self):
        instance = ModelWithCounter.objects.create()
        self.assertEqual(0, instance.counter.value())

        instance.counter.increment()
        self.assertEqual(1, instance.counter.value())

        instance.counter.increment()
        self.assertEqual(2, instance.counter.value())

        instance.counter.decrement()
        self.assertEqual(1, instance.counter.value())

        instance.counter.decrement()
        self.assertEqual(0, instance.counter.value())

    def test_negative_counts(self):
        instance = ModelWithCounter.objects.create()
        self.assertEqual(instance.counter.value(), 0)
        instance.counter.decrement(5)
        instance.counter.increment()
        self.assertEqual(instance.counter.value(), -4)

    def test_create_in_transaction(self):
        """ ShardedCounterField shouldn't prevent us from saving the model object inside a transaction.
        """
        with transaction.atomic():
            ModelWithCounter.objects.create()

    def test_increment_step(self):
        """ Test the behvaviour of incrementing in steps of more than 1. """
        instance = ModelWithCounter.objects.create()
        self.assertEqual(instance.counter.value(), 0)
        instance.counter.increment(3)
        instance.counter.increment(2)
        self.assertEqual(instance.counter.value(), 5)


    def test_decrement_step(self):
        """ Test the behvaviour of decrementing in steps of more than 1. """
        instance = ModelWithCounter.objects.create()
        self.assertEqual(instance.counter.value(), 0)
        instance.counter.increment(2)
        instance.counter.increment(7)
        instance.counter.increment(3)
        instance.counter.decrement(7)
        self.assertEqual(instance.counter.value(), 5)

    def test_reset(self):
        """ Test the behaviour of calling reset() on the field. """
        instance = ModelWithCounter.objects.create()
        self.assertEqual(instance.counter.value(), 0)
        instance.counter.increment(7)
        self.assertEqual(instance.counter.value(), 7)
        instance.counter.reset()
        self.assertEqual(instance.counter.value(), 0)

    def test_reset_negative_count(self):
        """ Test resetting a negative count. """
        instance = ModelWithCounter.objects.create()
        self.assertEqual(instance.counter.value(), 0)
        instance.counter.decrement(7)
        self.assertEqual(instance.counter.value(), -7)
        instance.counter.reset()
        self.assertEqual(instance.counter.value(), 0)

    def test_reset_with_many_shards(self):
        """ Test that even if the counter field has more shards than can be counted in a single
            transaction, that the `reset` method still works.
        """
        instance = ModelWithCounterWithManyShards.objects.create()
        instance.counter.populate()
        instance.counter.increment(5)
        instance.counter.reset()

    def test_populate(self):
        """ Test that the populate() method correctly generates all of the CounterShard objects. """
        instance = ModelWithCounter.objects.create()
        # Initially, none of the CounterShard objects should have been created
        self.assertEqual(len(instance.counter), 0)
        self.assertEqual(CounterShard.objects.count(), 0)
        instance.counter.populate()
        expected_num_shards = instance._meta.get_field('counter').shard_count
        self.assertEqual(len(instance.counter), expected_num_shards)

    def test_populate_is_idempotent_across_threads(self):
        """ Edge case test to make sure that 2 different threads calling .populate() on a field
            don't cause it to exceed the corrent number of shards.
        """
        instance = ModelWithCounter.objects.create()
        same_instance = ModelWithCounter.objects.get()
        instance.counter.populate()
        same_instance.counter.populate()
        # Now reload it from the DB and check that it has the correct number of shards
        instance = ModelWithCounter.objects.get()
        self.assertEqual(instance.counter.all().count(), DEFAULT_SHARD_COUNT)


    def test_label_reference_is_saved(self):
        """ Test that each CounterShard which the field creates is saved with the label of the
            model and field to which it belongs.
        """
        instance = ModelWithCounter.objects.create()
        instance.counter.populate()
        expected_shard_label = '%s.%s' % (ModelWithCounter._meta.db_table, 'counter')
        self.assertEqual(
            CounterShard.objects.filter(label=expected_shard_label).count(),
            len(instance.counter)
        )

    def test_many_counters_on_one_model(self):
        """ Test that have multiple counters on the same model doesn't cause any issues.
            This is mostly to test that the multiple reverse relations to the CounterShard model
            don't clash.
        """
        instance = ModelWithManyCounters.objects.create()
        instance.counter1.increment(5)
        instance.counter1.increment(5)
        instance.counter2.increment(1)
        self.assertEqual(instance.counter1.value(), 10)
        self.assertEqual(instance.counter2.value(), 1)
        instance.counter1.reset()
        self.assertEqual(instance.counter1.value(), 0)
        self.assertEqual(instance.counter2.value(), 1)


class IterableFieldTests(TestCase):
    def test_filtering_on_iterable_fields(self):
        list1 = IterableFieldModel.objects.create(
            list_field=['A', 'B', 'C', 'D', 'E', 'F', 'G'],
            set_field=set(['A', 'B', 'C', 'D', 'E', 'F', 'G']))
        list2 = IterableFieldModel.objects.create(
            list_field=['A', 'B', 'C', 'H', 'I', 'J'],
            set_field=set(['A', 'B', 'C', 'H', 'I', 'J']))

        # filtering using exact lookup with ListField:
        qry = IterableFieldModel.objects.filter(list_field='A')
        self.assertEqual(sorted(x.pk for x in qry), sorted([list1.pk, list2.pk]))
        qry = IterableFieldModel.objects.filter(list_field='H')
        self.assertEqual(sorted(x.pk for x in qry), [list2.pk,])

        # filtering using exact lookup with SetField:
        qry = IterableFieldModel.objects.filter(set_field='A')
        self.assertEqual(sorted(x.pk for x in qry), sorted([list1.pk, list2.pk]))
        qry = IterableFieldModel.objects.filter(set_field='H')
        self.assertEqual(sorted(x.pk for x in qry), [list2.pk,])

        # filtering using in lookup with ListField:
        qry = IterableFieldModel.objects.filter(list_field__in=['A', 'B', 'C'])
        self.assertEqual(sorted(x.pk for x in qry), sorted([list1.pk, list2.pk,]))
        qry = IterableFieldModel.objects.filter(list_field__in=['H', 'I', 'J'])
        self.assertEqual(sorted(x.pk for x in qry), sorted([list2.pk,]))

        # filtering using in lookup with SetField:
        qry = IterableFieldModel.objects.filter(set_field__in=set(['A', 'B']))
        self.assertEqual(sorted(x.pk for x in qry), sorted([list1.pk, list2.pk]))
        qry = IterableFieldModel.objects.filter(set_field__in=set(['H']))
        self.assertEqual(sorted(x.pk for x in qry), [list2.pk,])

    def test_empty_iterable_fields(self):
        """ Test that an empty set field always returns set(), not None """
        instance = IterableFieldModel()
        # When assigning
        self.assertEqual(instance.set_field, set())
        self.assertEqual(instance.list_field, [])
        instance.save()

        instance = IterableFieldModel.objects.get()
        # When getting it from the db
        self.assertEqual(instance.set_field, set())
        self.assertEqual(instance.list_field, [])

    def test_list_field(self):
        instance = IterableFieldModel.objects.create()
        self.assertEqual([], instance.list_field)
        instance.list_field.append("One")
        self.assertEqual(["One"], instance.list_field)
        instance.save()

        self.assertEqual(["One"], instance.list_field)

        instance = IterableFieldModel.objects.get(pk=instance.pk)
        self.assertEqual(["One"], instance.list_field)

        instance.list_field = None

        # Or anything else for that matter!
        with self.assertRaises(ValueError):
            instance.list_field = "Bananas"
            instance.save()

        results = IterableFieldModel.objects.filter(list_field="One")
        self.assertEqual([instance], list(results))

        self.assertEqual([1, 2], ListField(models.IntegerField).to_python("[1, 2]"))

    def test_set_field(self):
        instance = IterableFieldModel.objects.create()
        self.assertEqual(set(), instance.set_field)
        instance.set_field.add("One")
        self.assertEqual(set(["One"]), instance.set_field)
        instance.save()

        self.assertEqual(set(["One"]), instance.set_field)

        instance = IterableFieldModel.objects.get(pk=instance.pk)
        self.assertEqual(set(["One"]), instance.set_field)

        instance.set_field = None

        # Or anything else for that matter!
        with self.assertRaises(ValueError):
            instance.set_field = "Bananas"
            instance.save()

        self.assertEqual({1, 2}, SetField(models.IntegerField).to_python("{1, 2}"))

    def test_empty_list_queryable_with_is_null(self):
        instance = IterableFieldModel.objects.create()

        self.assertTrue(IterableFieldModel.objects.filter(set_field__isnull=True).exists())

        instance.set_field.add(1)
        instance.save()

        self.assertFalse(IterableFieldModel.objects.filter(set_field__isnull=True).exists())
        self.assertTrue(IterableFieldModel.objects.filter(set_field__isnull=False).exists())

        self.assertFalse(IterableFieldModel.objects.exclude(set_field__isnull=False).exists())
        self.assertTrue(IterableFieldModel.objects.exclude(set_field__isnull=True).exists())

    def test_assign_integer_throws_typeerror(self):
        self.assertRaises(TypeError, IterableFieldModel, list_field=1)
        self.assertRaises(TypeError, IterableFieldModel, set_field=1)

class InstanceListFieldTests(TestCase):

    def test_deserialization(self):
        i1 = ISOther.objects.create(pk=1)
        i2 = ISOther.objects.create(pk=2)
        # Does the to_python need to return ordered list? SetField test only passes because the set
        # happens to order it correctly
        self.assertItemsEqual([i1, i2], ISModel._meta.get_field("related_list").to_python("[1, 2]"))

    def test_save_and_load_empty(self):
        """
        Create a main object with no related items,
        get a copy of it back from the db and try to read items.
        """
        main = ISModel.objects.create()
        main_from_db = ISModel.objects.get(pk=main.pk)

        # Fetch the container from the database and read its items
        self.assertItemsEqual(main_from_db.related_list.all(), [])

    def test_basic_usage(self):
        main = ISModel.objects.create()
        other = ISOther.objects.create(name="test")
        other2 = ISOther.objects.create(name="test2")

        main.related_list.add(other)
        main.save()

        self.assertEqual([other.pk,], main.related_list_ids)
        self.assertEqual(list(ISOther.objects.filter(pk__in=main.related_list_ids)), list(main.related_list.all()))
        self.assertEqual([main], list(other.ismodel_list.all()))

        main.related_list.remove(other)
        self.assertFalse(main.related_list)

        main.related_list = [other2, ]
        self.assertEqual([other2.pk, ], main.related_list_ids)

        with self.assertRaises(AttributeError):
            other.ismodel_list = [main, ]

        without_reverse = RelationWithoutReverse.objects.create(name="test3")
        self.assertFalse(hasattr(without_reverse, "ismodel_list"))

    def test_add_to_empty(self):
        """
        Create a main object with no related items,
        get a copy of it back from the db and try to add items.
        """
        main = ISModel.objects.create()
        main_from_db = ISModel.objects.get(pk=main.pk)

        other = ISOther.objects.create()
        main_from_db.related_list.add(other)
        main_from_db.save()

    def test_add_another(self):
        """
        Create a main object with related items,
        get a copy of it back from the db and try to add more.
        """
        main = ISModel.objects.create()
        other1 = ISOther.objects.create()
        main.related_things.add(other1)
        main.save()

        main_from_db = ISModel.objects.get(pk=main.pk)
        other2 = ISOther.objects.create()

        main_from_db.related_list.add(other2)
        main_from_db.save()

    def test_multiple_objects(self):
        main = ISModel.objects.create()
        other1 = ISOther.objects.create()
        other2 = ISOther.objects.create()

        main.related_list.add(other1, other2)
        main.save()

        main_from_db = ISModel.objects.get(pk=main.pk)
        self.assertEqual(main_from_db.related_list.count(), 2)

    def test_deletion(self):
        """
        Delete one of the objects referred to by the related field
        """
        main = ISModel.objects.create()
        other = ISOther.objects.create()
        main.related_list.add(other)
        main.save()

        other.delete()
        self.assertEqual(main.related_list.count(), 0)

    def test_ordering_is_maintained(self):
        main = ISModel.objects.create()
        other = ISOther.objects.create()
        other1 = ISOther.objects.create()
        other2 = ISOther.objects.create()
        other3 = ISOther.objects.create()
        main.related_list.add(other, other1, other2, other3)
        main.save()
        self.assertEqual(main.related_list.count(), 4)
        self.assertEqual([other.pk, other1.pk, other2.pk, other3.pk, ], main.related_list_ids)
        self.assertItemsEqual([other, other1, other2, other3, ], main.related_list.all())
        main.related_list.clear()
        main.save()
        self.assertEqual([], main.related_list_ids)

    def test_duplicates_maintained(self):
        """
            For whatever reason you might want many of the same relation in the
            list
        """
        main = ISModel.objects.create()
        other = ISOther.objects.create()
        other1 = ISOther.objects.create()
        other2 = ISOther.objects.create()
        other3 = ISOther.objects.create()
        main.related_list.add(other, other1, other2, other1, other3,)
        main.save()
        self.assertEqual([other.pk, other1.pk, other2.pk, other1.pk, other3.pk, ], main.related_list_ids)
        self.assertItemsEqual([other, other1, other2, other1, other3, ], main.related_list.all())

    def test_slicing(self):
        main = ISModel.objects.create()
        other = ISOther.objects.create()
        other1 = ISOther.objects.create()
        other2 = ISOther.objects.create()
        other3 = ISOther.objects.create()
        main.related_list.add(other, other1, other2, other1, other3,)
        main.save()
        self.assertItemsEqual([other, other1, ], main.related_list.all()[:2])
        self.assertItemsEqual([other1, ], main.related_list.all()[1:2])
        self.assertEqual(other1, main.related_list.all()[1:2][0])

    def test_filtering(self):
        main = ISModel.objects.create()
        other = ISOther.objects.create(name="one")
        other1 = ISOther.objects.create(name="two")
        other2 = ISOther.objects.create(name="one")
        other3 = ISOther.objects.create(name="three")
        main.related_list.add(other, other1, other2, other1, other2,)
        main.save()
        self.assertItemsEqual([other, other2, other2], main.related_list.filter(name="one"))



class InstanceSetFieldTests(TestCase):

    def test_deserialization(self):
        i1 = ISOther.objects.create(pk=1)
        i2 = ISOther.objects.create(pk=2)

        self.assertEqual(set([i1, i2]), ISModel._meta.get_field("related_things").to_python("[1, 2]"))

    def test_basic_usage(self):
        main = ISModel.objects.create()
        other = ISOther.objects.create(name="test")
        other2 = ISOther.objects.create(name="test2")

        main.related_things.add(other)
        main.save()

        self.assertEqual({other.pk}, main.related_things_ids)
        self.assertEqual(list(ISOther.objects.filter(pk__in=main.related_things_ids)), list(main.related_things.all()))

        self.assertEqual([main], list(other.ismodel_set.all()))

        main.related_things.remove(other)
        self.assertFalse(main.related_things_ids)

        main.related_things = {other2}
        self.assertEqual({other2.pk}, main.related_things_ids)

        with self.assertRaises(AttributeError):
            other.ismodel_set = {main}

        without_reverse = RelationWithoutReverse.objects.create(name="test3")
        self.assertFalse(hasattr(without_reverse, "ismodel_set"))

    def test_save_and_load_empty(self):
        """
        Create a main object with no related items,
        get a copy of it back from the db and try to read items.
        """
        main = ISModel.objects.create()
        main_from_db = ISModel.objects.get(pk=main.pk)

        # Fetch the container from the database and read its items
        self.assertItemsEqual(main_from_db.related_things.all(), [])

    def test_add_to_empty(self):
        """
        Create a main object with no related items,
        get a copy of it back from the db and try to add items.
        """
        main = ISModel.objects.create()
        main_from_db = ISModel.objects.get(pk=main.pk)

        other = ISOther.objects.create()
        main_from_db.related_things.add(other)
        main_from_db.save()

    def test_add_another(self):
        """
        Create a main object with related items,
        get a copy of it back from the db and try to add more.
        """
        main = ISModel.objects.create()
        other1 = ISOther.objects.create()
        main.related_things.add(other1)
        main.save()

        main_from_db = ISModel.objects.get(pk=main.pk)
        other2 = ISOther.objects.create()

        main_from_db.related_things.add(other2)
        main_from_db.save()

    def test_multiple_objects(self):
        main = ISModel.objects.create()
        other1 = ISOther.objects.create()
        other2 = ISOther.objects.create()

        main.related_things.add(other1, other2)
        main.save()

        main_from_db = ISModel.objects.get(pk=main.pk)
        self.assertEqual(main_from_db.related_things.count(), 2)

    def test_deletion(self):
        """
        Delete one of the objects referred to by the related field
        """
        main = ISModel.objects.create()
        other = ISOther.objects.create()
        main.related_things.add(other)
        main.save()

        other.delete()
        self.assertEqual(main.related_things.count(), 0)

    def test_querying_with_isnull(self):
        obj = ISModel.objects.create()

        self.assertItemsEqual([obj], ISModel.objects.filter(related_things__isnull=True))
        self.assertItemsEqual([obj], ISModel.objects.filter(related_things_ids__isnull=True))


class TestGenericRelationField(TestCase):
    def test_basic_usage(self):
        instance = GenericRelationModel.objects.create()
        self.assertIsNone(instance.relation_to_anything)

        thing = ISOther.objects.create()
        instance.relation_to_anything = thing
        instance.save()

        self.assertTrue(instance.relation_to_anything_id)

        instance = GenericRelationModel.objects.get()
        self.assertEqual(thing, instance.relation_to_anything)

    def test_overridden_dbtable(self):
        """ Check that the related object having a custom `db_table` doesn't affect the functionality. """
        instance = GenericRelationModel.objects.create()
        self.assertIsNone(instance.relation_to_anything)

        weird = RelationWithOverriddenDbTable.objects.create()
        instance.relation_to_anything = weird
        instance.save()

        self.assertTrue(instance.relation_to_anything)

        instance = GenericRelationModel.objects.get()
        self.assertEqual(weird, instance.relation_to_anything)

    def test_querying(self):
        thing = ISOther.objects.create()
        instance = GenericRelationModel.objects.create(relation_to_anything=thing)
        self.assertEqual(GenericRelationModel.objects.filter(relation_to_anything=thing)[0], instance)

    def test_unique(self):
        thing = ISOther.objects.create()
        instance = GenericRelationModel.objects.create(unique_relation_to_anything=thing)
        # Trying to create another instance which relates to the same 'thing' should fail
        self.assertRaises(IntegrityError, GenericRelationModel.objects.create, unique_relation_to_anything=thing)
        # But creating 2 objects which both have `unique_relation_to_anything` set to None should be fine
        instance.unique_relation_to_anything = None
        instance.save()
        GenericRelationModel.objects.create(unique_relation_to_anything=None)
        GenericRelationModel.objects.create() # It should work even if we don't explicitly set it to None


class JSONFieldModelTests(TestCase):

    def test_object_pairs_hook_with_ordereddict(self):
        items = [('first', 1), ('second', 2), ('third', 3), ('fourth', 4)]
        od = OrderedDict(items)

        thing = JSONFieldModel(json_field=od)
        thing.save()

        thing = JSONFieldModel.objects.get()
        self.assertEqual(od, thing.json_field)

    def test_object_pairs_hook_with_normal_dict(self):
        """
        Check that dict is not stored as OrderedDict if
        object_pairs_hook is not set
        """

        # monkey patch field
        field = JSONFieldModel._meta.get_field('json_field')
        field.use_ordered_dict = False

        normal_dict = {'a': 1, 'b': 2, 'c': 3}

        thing = JSONFieldModel(json_field=normal_dict)
        self.assertFalse(isinstance(thing.json_field, OrderedDict))
        thing.save()

        thing = JSONFieldModel.objects.get()
        self.assertFalse(isinstance(thing.json_field, OrderedDict))

        field.use_ordered_dict = True
