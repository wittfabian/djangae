from djangae.test import TestCase

from djangae.db import transaction
from djangae.contrib import sleuth

from .test_connector import TestUser, TestFruit


class TransactionTests(TestCase):
    def test_atomic_decorator(self):

        @transaction.atomic
        def txn():
            TestUser.objects.create(username="foo", field2="bar")
            self.assertTrue(transaction.in_atomic_block())
            raise ValueError()

        with self.assertRaises(ValueError):
            txn()

        self.assertEqual(0, TestUser.objects.count())

    def test_interaction_with_datastore_txn(self):
        from google.appengine.ext import db
        from google.appengine.datastore.datastore_rpc import TransactionOptions

        @db.transactional(propagation=TransactionOptions.INDEPENDENT)
        def some_indie_txn(_username):
            TestUser.objects.create(username=_username)

        @db.transactional()
        def some_non_indie_txn(_username):
            TestUser.objects.create(username=_username)

        @db.transactional()
        def double_nested_transactional():
            @db.transactional(propagation=TransactionOptions.INDEPENDENT)
            def do_stuff():
                TestUser.objects.create(username="Double")
                raise ValueError()

            try:
                return do_stuff
            except:
                return

        with transaction.atomic():
            double_nested_transactional()


        @db.transactional()
        def something_containing_atomic():
            with transaction.atomic():
                TestUser.objects.create(username="Inner")

        something_containing_atomic()

        with transaction.atomic():
            with transaction.atomic():
                some_non_indie_txn("Bob1")
                some_indie_txn("Bob2")
                some_indie_txn("Bob3")

        with transaction.atomic(independent=True):
            some_non_indie_txn("Fred1")
            some_indie_txn("Fred2")
            some_indie_txn("Fred3")

    def test_atomic_context_manager(self):

        with self.assertRaises(ValueError):
            with transaction.atomic():
                TestUser.objects.create(username="foo", field2="bar")
                raise ValueError()

        self.assertEqual(0, TestUser.objects.count())


    def test_non_atomic_context_manager(self):
        existing = TestUser.objects.create(username="existing", field2="exists")

        with transaction.atomic():
            self.assertTrue(transaction.in_atomic_block())

            user = TestUser.objects.create(username="foo", field2="bar")

            with transaction.non_atomic():
                # We're outside the transaction, so the user should not exist
                self.assertRaises(TestUser.DoesNotExist, TestUser.objects.get, pk=user.pk)
                self.assertFalse(transaction.in_atomic_block())

                with sleuth.watch("google.appengine.api.datastore.Get") as datastore_get:
                    TestUser.objects.get(pk=existing.pk) #Should hit the cache, not the datastore

                self.assertFalse(datastore_get.called)

            with transaction.atomic(independent=True):
                user2 = TestUser.objects.create(username="foo2", field2="bar2")
                self.assertTrue(transaction.in_atomic_block())

                with transaction.non_atomic():
                    self.assertFalse(transaction.in_atomic_block())
                    self.assertRaises(TestUser.DoesNotExist, TestUser.objects.get, pk=user2.pk)

                    with transaction.non_atomic():
                        self.assertFalse(transaction.in_atomic_block())
                        self.assertRaises(TestUser.DoesNotExist, TestUser.objects.get, pk=user2.pk)

                    self.assertFalse(transaction.in_atomic_block())
                    self.assertRaises(TestUser.DoesNotExist, TestUser.objects.get, pk=user2.pk)

                self.assertTrue(TestUser.objects.filter(pk=user2.pk).exists())
                self.assertTrue(transaction.in_atomic_block())


    def test_xg_argument(self):

        @transaction.atomic(xg=True)
        def txn(_username):
            TestUser.objects.create(username=_username, field2="bar")
            TestFruit.objects.create(name="Apple", color="pink")
            raise ValueError()

        with self.assertRaises(ValueError):
            txn("foo")

        self.assertEqual(0, TestUser.objects.count())
        self.assertEqual(0, TestFruit.objects.count())

    def test_independent_argument(self):
        """
            We would get a XG error if the inner transaction was not independent
        """

        @transaction.atomic
        def txn1(_username, _fruit):
            @transaction.atomic(independent=True)
            def txn2(_fruit):
                TestFruit.objects.create(name=_fruit, color="pink")
                raise ValueError()

            TestUser.objects.create(username=_username)
            txn2(_fruit)


        with self.assertRaises(ValueError):
            txn1("test", "banana")
