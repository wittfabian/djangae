from djangae.test import TestCase
from djangae.db.backends.appengine.context import ContextStack
from google.appengine.api import datastore

class FakeEntity(dict):
    def key(self):
        return datastore.Key.from_path("fake", 1)

class ContextStackTests(TestCase):

    def test_push_pop(self):
        stack = ContextStack()

        self.assertEqual({}, stack.top.cache)

        entity = FakeEntity()
        entity["bananas"] = 1

        stack.top.cache_entity(["bananas:1"], entity)

        self.assertEqual({"bananas": 1}, stack.top.cache.values()[0])

        stack.push()

        self.assertEqual({"bananas": 1}, stack.top.cache.values()[0])
        self.assertEqual(2, stack.size)

        stack.push()

        stack.top.cache_entity(["apples:2"], entity)

        self.assertItemsEqual(["bananas:1", "apples:2"], stack.top.cache.keys())

        stack.pop()

        self.assertItemsEqual(["bananas:1"], stack.top.cache.keys())
        self.assertEqual({"bananas": 1}, stack.top.cache["bananas:1"])
        self.assertEqual(2, stack.size)
        self.assertEqual(1, stack.staged_count)

        updated = FakeEntity()
        updated["bananas"] = 3

        stack.top.cache_entity(["bananas:1"], updated)

        stack.pop(apply_staged=True, clear_staged=True)

        self.assertEqual(1, stack.size)
        self.assertEqual({"bananas": 3}, stack.top.cache["bananas:1"])
        self.assertEqual(0, stack.staged_count)

    def test_property_deletion(self):
        stack = ContextStack()

        entity = FakeEntity()
        entity["field1"] = "one"
        entity["field2"] = "two"

        stack.top.cache_entity(["entity"], entity)

        stack.push() # Enter transaction

        entity["field1"] = "oneone"
        del entity["field2"]

        stack.top.cache_entity(["entity"], entity)

        stack.pop(apply_staged=True, clear_staged=True)

        self.assertEqual({"field1": "oneone"}, stack.top.cache["entity"])





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

    def test_save_caches_outside_transaction(self):
        pass

    def test_save_doesnt_cache_inside_transaction(self):
        pass

    def test_save_wipes_entity_from_cache_inside_transaction(self):
        pass

    def test_consistent_read_updates_memcache_outside_transaction(self):
        pass

    def test_eventual_read_doesnt_update_memcache(self):
        pass

    def test_unique_filter_hits_memcache(self):
        pass

    def test_get_by_key_hits_memcache(self):
        pass

    def test_unique_get_hits_memcache(self):
        pass

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

    def test_transactions_get_their_own_context(self):
        pass

    def test_nested_transaction_doesnt_apply_to_outer_context(self):
        pass

    def test_outermost_transaction_applies_all_contexts_on_commit(self):
        pass

    def test_context_wiped_on_rollback(self):
        pass

    def test_save_caches(self):
        pass

    def test_consistent_read_updates_cache(self):
        pass

    def test_inconsistent_read_doesnt_update_cache(self):
        pass

    def test_unique_filter_hits_cache(self):
        pass

    def test_get_by_key_hits_cache(self):
        pass

    def test_unique_get_hits_cache(self):
        pass
