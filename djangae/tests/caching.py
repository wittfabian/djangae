import unittest

from google.appengine.api import datastore
from google.appengine.api import datastore_errors

from django.db import models
from django.http import HttpRequest
from django.core.signals import request_finished, request_started
from django.core.cache import cache

from djangae.contrib import sleuth
from djangae.test import TestCase
from djangae.db import unique_utils
from djangae.db import transaction
from djangae.db.backends.appengine.context import ContextStack
from djangae.db.backends.appengine import caching
from djangae.db.caching import disable_cache, clear_context_cache


class FakeEntity(dict):
    COUNTER = 1

    def __init__(self, data, id=0):
        self.id = id or FakeEntity.COUNTER
        FakeEntity.COUNTER += 1
        self.update(data)

    def key(self):
        return datastore.Key.from_path("table", self.id)


class ContextStackTests(TestCase):

    def test_push_pop(self):
        stack = ContextStack()

        self.assertEqual({}, stack.top.cache)

        entity = FakeEntity({"bananas": 1})

        stack.top.cache_entity(["bananas:1"], entity, caching.CachingSituation.DATASTORE_PUT)

        self.assertEqual({"bananas": 1}, stack.top.cache.values()[0])

        stack.push()

        self.assertEqual([], stack.top.cache.values())
        self.assertEqual(2, stack.size)

        stack.push()

        stack.top.cache_entity(["apples:2"], entity, caching.CachingSituation.DATASTORE_PUT)

        self.assertItemsEqual(["apples:2"], stack.top.cache.keys())

        stack.pop()

        self.assertItemsEqual([], stack.top.cache.keys())
        self.assertEqual(2, stack.size)
        self.assertEqual(1, stack.staged_count)

        updated = FakeEntity({"bananas": 3})

        stack.top.cache_entity(["bananas:1"], updated, caching.CachingSituation.DATASTORE_PUT)

        stack.pop(apply_staged=True, clear_staged=True)

        self.assertEqual(1, stack.size)
        self.assertEqual({"bananas": 3}, stack.top.cache["bananas:1"])
        self.assertEqual(0, stack.staged_count)

    def test_property_deletion(self):
        stack = ContextStack()

        entity = FakeEntity({"field1": "one", "field2": "two"})

        stack.top.cache_entity(["entity"], entity, caching.CachingSituation.DATASTORE_PUT)

        stack.push() # Enter transaction

        entity["field1"] = "oneone"
        del entity["field2"]

        stack.top.cache_entity(["entity"], entity, caching.CachingSituation.DATASTORE_PUT)

        stack.pop(apply_staged=True, clear_staged=True)

        self.assertEqual({"field1": "oneone"}, stack.top.cache["entity"])



class CachingTestModel(models.Model):

    field1 = models.CharField(max_length=255, unique=True)
    comb1 = models.IntegerField(default=0)
    comb2 = models.CharField(max_length=255)

    class Meta:
        unique_together = [
            ("comb1", "comb2")
        ]

        app_label = "djangae"


class MemcacheCachingTests(TestCase):
    """
        We need to be pretty selective with our caching in memcache, because unlike
        the context caching, this stuff is global.

        For that reason, we have the following rules:

         - save/update caches entities outside transactions
         - Inside transactions save/update wipes out the cache for updated entities (a subsequent read by key will populate it again)
         - Inside transactions filter/get does not hit memcache (that just breaks transactions)
         - filter/get by key caches entities (consistent)
         - filter/get by anything else does not (eventually consistent)
    """

    @disable_cache(memcache=False, context=True)
    def test_save_caches_outside_transaction_only(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        identifiers = unique_utils.unique_identifiers_from_entity(CachingTestModel, FakeEntity(entity_data, id=222))

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        instance = CachingTestModel.objects.create(id=222, **entity_data)

        for identifier in identifiers:
            self.assertEqual(entity_data, cache.get(identifier))

        instance.delete()

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        with transaction.atomic():
            instance = CachingTestModel.objects.create(**entity_data)


        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

    @disable_cache(memcache=False, context=True)
    def test_save_wipes_entity_from_cache_inside_transaction(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        identifiers = unique_utils.unique_identifiers_from_entity(CachingTestModel, FakeEntity(entity_data, id=222))

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        instance = CachingTestModel.objects.create(id=222, **entity_data)

        for identifier in identifiers:
            self.assertEqual(entity_data, cache.get(identifier))

        with transaction.atomic():
            instance.save()

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

    @disable_cache(memcache=False, context=True)
    def test_consistent_read_updates_memcache_outside_transaction(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        identifiers = unique_utils.unique_identifiers_from_entity(CachingTestModel, FakeEntity(entity_data, id=222))

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        CachingTestModel.objects.create(id=222, **entity_data)

        for identifier in identifiers:
            self.assertEqual(entity_data, cache.get(identifier))

        cache.clear()

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        CachingTestModel.objects.get(id=222) # Consistent read

        for identifier in identifiers:
            self.assertEqual(entity_data, cache.get(identifier))

    @disable_cache(memcache=False, context=True)
    def test_eventual_read_doesnt_update_memcache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        identifiers = unique_utils.unique_identifiers_from_entity(CachingTestModel, FakeEntity(entity_data, id=222))

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        CachingTestModel.objects.create(id=222, **entity_data)

        for identifier in identifiers:
            self.assertEqual(entity_data, cache.get(identifier))

        cache.clear()

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

        CachingTestModel.objects.all()[0] # Inconsistent read

        for identifier in identifiers:
            self.assertIsNone(cache.get(identifier))

    @disable_cache(memcache=False, context=True)
    def test_unique_filter_hits_memcache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Query.Run") as datastore_query:
            instance = CachingTestModel.objects.filter(field1="Apple").all()[0]
            self.assertEqual(original, instance)

        self.assertFalse(datastore_query.called)

    @disable_cache(memcache=False, context=True)
    def test_non_unique_filter_hits_datastore(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Query.Run") as datastore_query:
            instance = CachingTestModel.objects.filter(comb1=1).all()[0]
            self.assertEqual(original, instance)

        self.assertTrue(datastore_query.called)

    @disable_cache(memcache=False, context=True)
    def test_get_by_key_hits_memcache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            instance = CachingTestModel.objects.get(pk=original.pk)
            self.assertEqual(original, instance)

        self.assertFalse(datastore_get.called)

    @disable_cache(memcache=False, context=True)
    def test_get_by_key_hits_datastore_inside_transaction(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            with transaction.atomic():
                instance = CachingTestModel.objects.get(pk=original.pk)
            self.assertEqual(original, instance)

        self.assertTrue(datastore_get.called)

    @disable_cache(memcache=False, context=True)
    def test_unique_get_hits_memcache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            instance = CachingTestModel.objects.get(field1="Apple")
            self.assertEqual(original, instance)

        self.assertFalse(datastore_get.called)

    @disable_cache(memcache=False, context=True)
    def test_unique_get_hits_datastore_inside_transaction(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Query.Run") as datastore_query:
            with transaction.atomic():
                try:
                    CachingTestModel.objects.get(field1="Apple")
                except datastore_errors.BadRequestError:
                    # You can't query in a transaction, but still
                    pass

        self.assertTrue(datastore_query.called)

class ContextCachingTests(TestCase):
    """
        We can be a bit more liberal with hitting the context cache as it's
        thread-local and request-local

        The context cache is actually a stack. When you start a transaction we push a
        copy of the current context onto the stack, when we finish a transaction we pop
        the current context and apply the changes onto the outer transaction.

        The rules are thus:

        - Entering a transaction pushes a copy of the current context
        - Rolling back a transaction pops the top of the stack
        - Committing a transaction pops the top of the stack, and adds it to a queue
        - When all transactions exit, the queue is applied to the current context one at a time
        - save/update caches entities
        - filter/get by key caches entities (consistent)
        - filter/get by anything else does not (eventually consistent)
    """

    @disable_cache(memcache=True, context=False)
    def test_caching_bug(self):
        entity_data = {
            "field1": u"Apple",
            "comb1": 1,
            "comb2": u"Cherry"
        }

        instance = CachingTestModel.objects.create(**entity_data)

        expected = entity_data.copy()
        expected[u"id"] = instance.pk

        # Fetch the object, which causes it to be added to the context cache
        self.assertItemsEqual(CachingTestModel.objects.filter(pk=instance.pk).values(), [expected])
        # Doing a .values_list() fetches from the cache and wipes out the other fields from the entity
        self.assertItemsEqual(CachingTestModel.objects.filter(pk=instance.pk).values_list("field1"), [("Apple",)])
        # Now fetch from the cache again, checking that the previously wiped fields are still in tact
        self.assertItemsEqual(CachingTestModel.objects.filter(pk=instance.pk).values(), [expected])


    @disable_cache(memcache=True, context=False)
    def test_transactions_get_their_own_context(self):
        with sleuth.watch("djangae.db.backends.appengine.context.ContextStack.push") as context_push:
            with transaction.atomic():
                pass

            self.assertTrue(context_push.called)

    @disable_cache(memcache=True, context=False)
    def test_nested_transaction_doesnt_apply_to_outer_context(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)
        with transaction.atomic():
            with transaction.atomic(independent=True):
                inner = CachingTestModel.objects.get(pk=original.pk)
                inner.field1 = "Banana"
                inner.save()

            outer = CachingTestModel.objects.get(pk=original.pk)
            self.assertEqual("Apple", outer.field1)

        original = CachingTestModel.objects.get(pk=original.pk)
        self.assertEqual("Banana", original.field1)

    @unittest.skip("The datastore seems broken, see: https://code.google.com/p/googleappengine/issues/detail?id=11631&thanks=11631&ts=1422376783")
    @disable_cache(memcache=True, context=False)
    def test_outermost_transaction_applies_all_contexts_on_commit(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        with transaction.atomic():
            with transaction.atomic(independent=True):
                instance = CachingTestModel.objects.create(**entity_data)

            # At this point the instance should be unretrievable, even though we just created it
            try:
                CachingTestModel.objects.get(pk=instance.pk)
                self.fail("Unexpectedly was able to retrieve instance")
            except CachingTestModel.DoesNotExist:
                pass

        # Should now exist in the cache
        with sleuth.switch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(pk=instance.pk)
            self.assertFalse(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_nested_rollback_doesnt_apply_on_outer_commit(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)
        with transaction.atomic():
            try:
                with transaction.atomic(independent=True):
                    inner = CachingTestModel.objects.get(pk=original.pk)
                    inner.field1 = "Banana"
                    inner.save()
                    raise ValueError() # Will rollback the transaction
            except ValueError:
                pass

            outer = CachingTestModel.objects.get(pk=original.pk)
            self.assertEqual("Apple", outer.field1)

        original = CachingTestModel.objects.get(pk=original.pk)
        self.assertEqual("Apple", original.field1) # Shouldn't have changed

    @disable_cache(memcache=True, context=False)
    def test_save_caches(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            with sleuth.watch("django.core.cache.cache.get") as memcache_get:
                original = CachingTestModel.objects.get(pk=original.pk)

        self.assertFalse(datastore_get.called)
        self.assertFalse(memcache_get.called)

    @disable_cache(memcache=True, context=False)
    def test_consistent_read_updates_cache_outside_transaction(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        clear_context_cache()

        CachingTestModel.objects.get(pk=original.pk) # Should update the cache

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(pk=original.pk)

        self.assertFalse(datastore_get.called)

        clear_context_cache()

        with transaction.atomic():
            with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
                CachingTestModel.objects.get(pk=original.pk) # Should *not* update the cache
                self.assertTrue(datastore_get.called)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(pk=original.pk)

        self.assertTrue(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_inconsistent_read_doesnt_update_cache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        clear_context_cache()

        CachingTestModel.objects.all() # Inconsistent

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(pk=original.pk)

        self.assertTrue(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_unique_filter_hits_cache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            list(CachingTestModel.objects.filter(field1="Apple"))

        self.assertFalse(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_get_by_key_hits_cache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        original = CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(pk=original.pk)

        self.assertFalse(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_unique_get_hits_cache(self):
        entity_data = {
            "field1": "Apple",
            "comb1": 1,
            "comb2": "Cherry"
        }

        CachingTestModel.objects.create(**entity_data)

        with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
            CachingTestModel.objects.get(field1="Apple")

        self.assertFalse(datastore_get.called)

    @disable_cache(memcache=True, context=False)
    def test_context_cache_cleared_after_request(self):
        """ The context cache should be cleared between requests. """
        CachingTestModel.objects.create(field1="test")
        with sleuth.watch("google.appengine.api.datastore.Query.Run") as query:
            CachingTestModel.objects.get(field1="test")
            self.assertEqual(query.call_count, 0)
            # Now start a new request, which should clear the cache
            request_started.send(HttpRequest(), keep_disabled_flags=True)
            CachingTestModel.objects.get(field1="test")
            self.assertEqual(query.call_count, 1)
            # Now do another call, which should use the cache (because it would have been
            # populated by the previous call)
            CachingTestModel.objects.get(field1="test")
            self.assertEqual(query.call_count, 1)
            # Now clear the cache again by *finishing* a request
            request_finished.send(HttpRequest(), keep_disabled_flags=True)
            CachingTestModel.objects.get(field1="test")
            self.assertEqual(query.call_count, 2)
