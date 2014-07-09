from cStringIO import StringIO
import datetime
import unittest
from string import letters

# LIBRARIES
from django.core.files.uploadhandler import StopFutureHandlers
from django.db import IntegrityError, models
from django.db.models.query import Q
from django.test import TestCase, RequestFactory
from google.appengine.api.datastore_errors import EntityNotFoundError

# DJANGAE
from djangae.db.exceptions import NotSupportedError
from djangae.indexing import add_special_index
from djangae.db.utils import entity_matches_query
from .storage import BlobstoreFileUploadHandler

from google.appengine.api import datastore

class TestUser(models.Model):
    username = models.CharField(max_length=32)
    email = models.EmailField()
    last_login = models.DateField()

    def __unicode__(self):
        return self.username

class Permission(models.Model):
    user = models.ForeignKey(TestUser)
    perm = models.CharField(max_length=32)

    def __unicode__(self):
        return u"{0} for {1}".format(self.perm, self.user)

    class Meta:
        ordering = ('user__username', 'perm')

class MultiTableParent(models.Model):
    parent_field = models.CharField(max_length=32)


class MultiTableChildOne(MultiTableParent):
    child_one_field = models.CharField(max_length=32)


class MultiTableChildTwo(MultiTableParent):
    child_two_field = models.CharField(max_length=32)


class BackendTests(TestCase):
    def test_entity_matches_query(self):
        entity = datastore.Entity("test_model")
        entity["name"] = "Charlie"
        entity["age"] = 22

        query = datastore.Query("test_model")
        query["name ="] = "Charlie"
        self.assertTrue(entity_matches_query(entity, query))

        query["age >="] = 5
        self.assertTrue(entity_matches_query(entity, query))
        del query["age >="]

        query["age <"] = 22
        self.assertFalse(entity_matches_query(entity, query))
        del query["age <"]

        query["age <="] = 22
        self.assertTrue(entity_matches_query(entity, query))
        del query["age <="]

        query["name ="] = "Fred"
        self.assertFalse(entity_matches_query(entity, query))

        #If the entity has a list field, then if any of them match the
        #query then it's a match
        entity["name"] = [ "Bob", "Fred", "Dave" ]
        self.assertTrue(entity_matches_query(entity, query)) #ListField test


class EdgeCaseTests(TestCase):
    def setUp(self):
        add_special_index(TestUser, "username", "iexact")

        self.u1 = TestUser.objects.create(username="A", email="test@example.com", last_login=datetime.datetime.now().date())
        self.u2 = TestUser.objects.create(username="B", email="test@example.com", last_login=datetime.datetime.now().date())
        TestUser.objects.create(username="C", email="test2@example.com", last_login=datetime.datetime.now().date())
        TestUser.objects.create(username="D", email="test3@example.com", last_login=datetime.datetime.now().date())
        TestUser.objects.create(username="E", email="test3@example.com", last_login=datetime.datetime.now().date())

    def test_multi_table_inheritance(self):

        parent = MultiTableParent.objects.create(parent_field="parent1")
        child1 = MultiTableChildOne.objects.create(parent_field="child1", child_one_field="child1")
        child2 = MultiTableChildTwo.objects.create(parent_field="child2", child_two_field="child2")

        self.assertEqual(3, MultiTableParent.objects.count())
        self.assertItemsEqual([parent.pk, child1.pk, child2.pk],
            list(MultiTableParent.objects.values_list('pk', flat=True)))
        self.assertEqual(1, MultiTableChildOne.objects.count())
        self.assertEqual(child1, MultiTableChildOne.objects.get())

        self.assertEqual(1, MultiTableChildTwo.objects.count())
        self.assertEqual(child2, MultiTableChildTwo.objects.get())

    def test_anding_pks(self):
        results = TestUser.objects.filter(id__exact=self.u1.pk).filter(id__exact=self.u2.pk)
        self.assertEqual(list(results), [])

    def test_unusual_queries(self):
        results = TestUser.objects.all()
        self.assertEqual(5, len(results))

        results = TestUser.objects.filter(username__in=["A", "B"])
        self.assertEqual(2, len(results))
        self.assertItemsEqual(["A", "B"], [x.username for x in results])

        results = TestUser.objects.filter(username__in=["A", "B"]).exclude(username="A")
        self.assertEqual(1, len(results), results)
        self.assertItemsEqual(["B"], [x.username for x in results])

        results = TestUser.objects.filter(username__lt="E")
        self.assertEqual(4, len(results))
        self.assertItemsEqual(["A", "B", "C", "D"], [x.username for x in results])

        results = TestUser.objects.filter(username__lte="E")
        self.assertEqual(5, len(results))

        #Double exclude not supported
        with self.assertRaises(NotSupportedError):
            list(TestUser.objects.exclude(username="E").exclude(username="A"))

        results = TestUser.objects.filter(username="A", email="test@example.com")
        self.assertEqual(1, len(results))

        results = TestUser.objects.filter(username__in=["A", "B"]).filter(username__in=["A", "B"])
        self.assertEqual(2, len(results))
        self.assertItemsEqual(["A", "B"], [x.username for x in results])

        results = TestUser.objects.filter(username__in=["A", "B"]).filter(username__in=["A"])
        self.assertEqual(1, len(results))
        self.assertItemsEqual(["A"], [x.username for x in results])

        results = TestUser.objects.filter(pk__in=[self.u1.pk, self.u2.pk]).filter(username__in=["A"])
        self.assertEqual(1, len(results))
        self.assertItemsEqual(["A"], [x.username for x in results])

        results = TestUser.objects.filter(username__in=["A"]).filter(pk__in=[self.u1.pk, self.u2.pk])
        self.assertEqual(1, len(results))
        self.assertItemsEqual(["A"], [x.username for x in results])

        #Negated in not supported
        with self.assertRaises(NotSupportedError):
            list(TestUser.objects.all().exclude(username__in=["A"]))

    @unittest.skip("We need to properly implement OR queries")
    def test_or_queryset(self):
        """
            This constructs an OR query, this is currently broken in the parse_where_and_check_projection
            function. WE MUST FIX THIS!
        """
        q1 = TestUser.objects.filter(username="A")
        q2 = TestUser.objects.filter(username="B")

        self.assertItemsEqual([self.u1, self.u2], list(q1 | q2))

    @unittest.skip("We need to properly implement OR queries")
    def test_or_q_objects(self):
        """ Test use of Q objects in filters. """
        query = TestUser.objects.filter(Q(username="A") | Q(username="B"))
        self.assertItemsEqual([self.u1, self.u2], list(query))

    def test_extra_select(self):
        results = TestUser.objects.filter(username='A').extra(select={'is_a': "username = 'A'"})
        self.assertEqual(1, len(results))
        self.assertItemsEqual([True], [x.is_a for x in results])

        results = TestUser.objects.all().exclude(username='A').extra(select={'is_a': "username = 'A'"})
        self.assertEqual(4, len(results))
        self.assertEqual(not any([x.is_a for x in results]), True)

        # Up for debate
        # results = User.objects.all().extra(select={'truthy': 'TRUE'})
        # self.assertEqual(all([x.truthy for x in results]), True)

        results = TestUser.objects.all().extra(select={'truthy': True})
        self.assertEqual(all([x.truthy for x in results]), True)


    def test_counts(self):
        self.assertEqual(5, TestUser.objects.count())
        self.assertEqual(2, TestUser.objects.filter(email="test3@example.com").count())
        self.assertEqual(3, TestUser.objects.exclude(email="test3@example.com").count())
        self.assertEqual(1,
            TestUser.objects.filter(username="A").exclude(email="test3@example.com").count())

        with self.assertRaises(NotSupportedError):
            list(TestUser.objects.exclude(username="E").exclude(username="A"))


    def test_deletion(self):
        count = TestUser.objects.count()

        self.assertTrue(count)

        TestUser.objects.filter(username="A").delete()

        self.assertEqual(count - 1, TestUser.objects.count())

        TestUser.objects.filter(username="B").exclude(username="B").delete() #Should do nothing

        self.assertEqual(count - 1, TestUser.objects.count())

        TestUser.objects.all().delete()

        count = TestUser.objects.count()

        self.assertFalse(count)

    def test_insert_with_existing_key(self):
        user = TestUser.objects.create(id=1, username="test1", last_login=datetime.datetime.now().date())
        self.assertEqual(1, user.pk)

        with self.assertRaises(IntegrityError):
            TestUser.objects.create(id=1, username="test2", last_login=datetime.datetime.now().date())

    def test_included_pks(self):
        ids = [ TestUser.objects.get(username="B").pk, TestUser.objects.get(username="A").pk ]
        results = TestUser.objects.filter(pk__in=ids).order_by("username")

        self.assertEqual(results[0], self.u1)
        self.assertEqual(results[1], self.u2)

    def test_select_related(self):
        """ select_related should be a no-op... for now """
        user = TestUser.objects.get(username="A")
        perm = Permission.objects.create(user=user, perm="test_perm")
        select_related = [ (p.perm, p.user.username) for p in user.permission_set.select_related() ]
        self.assertEqual(user.username, select_related[0][1])

    def test_cross_selects(self):
        user = TestUser.objects.get(username="A")
        perm = Permission.objects.create(user=user, perm="test_perm")
        with self.assertRaises(NotSupportedError):
            perms = list(Permission.objects.all().values_list("user__username", "perm"))
            self.assertEqual("A", perms[0][0])

    def test_values_list_on_pk_does_keys_only_query(self):
        from google.appengine.api.datastore import Query

        def replacement_init(*args, **kwargs):
            replacement_init.called_args = args
            replacement_init.called_kwargs = kwargs

        replacement_init.called_args = None
        replacement_init.called_kwargs = None

        try:
            original_init = Query.__init__
            Query.__init__ = replacement_init
            list(TestUser.objects.all().values_list('pk', flat=True))
        finally:
            Query.__init__ = original_init

        self.assertTrue(replacement_init.called_kwargs.get('keys_only'))
        self.assertEqual(5, len(TestUser.objects.all().values_list('pk')))

    def test_iexact(self):
        user = TestUser.objects.get(username__iexact="a")
        self.assertEqual("A", user.username)

    def test_ordering(self):
        users = TestUser.objects.all().order_by("username")

        self.assertEqual(["A", "B", "C", "D", "E"], [x.username for x in users])

        users = TestUser.objects.all().order_by("-username")

        self.assertEqual(["A", "B", "C", "D", "E"][::-1], [x.username for x in users])

    def test_dates_query(self):
        TestUser.objects.create(username="Z", email="z@example.com", last_login=datetime.date(2013, 4, 5))

        last_a_login = TestUser.objects.get(username="A").last_login

        dates = TestUser.objects.dates('last_login', 'year')
        self.assertItemsEqual(
            [datetime.datetime(2013, 1, 1, 0, 0), datetime.datetime(last_a_login.year, 1, 1, 0, 0)],
            dates
        )

        dates = TestUser.objects.dates('last_login', 'month')
        self.assertItemsEqual(
            [datetime.datetime(2013, 4, 1, 0, 0), datetime.datetime(last_a_login.year, last_a_login.month, 1, 0, 0)],
            dates
        )

        dates = TestUser.objects.dates('last_login', 'day')
        self.assertItemsEqual(
            [datetime.datetime(2013, 4, 5, 0, 0), datetime.datetime.combine(last_a_login, datetime.datetime.min.time())],
            dates
        )

        dates = TestUser.objects.dates('last_login', 'day', order='DESC')
        self.assertItemsEqual(
            [datetime.datetime.combine(last_a_login, datetime.datetime.min.time()), datetime.datetime(2013, 4, 5, 0, 0)],
            dates
        )

    def test_in_query(self):
        """ Test that the __in filter works, and that it cannot be used with more than 30 values,
            unless it's used on the PK field.
        """
        # Check that a basic __in query works
        results = list(TestUser.objects.filter(username__in=['A', 'B']))
        self.assertItemsEqual(results, [self.u1, self.u2])
        # Check that it also works on PKs
        results = list(TestUser.objects.filter(pk__in=[self.u1.pk, self.u2.pk]))
        self.assertItemsEqual(results, [self.u1, self.u2])
        # Check that using more than 30 items in an __in query not on the pk causes death
        query = TestUser.objects.filter(username__in=list([x for x in letters[:31]]))
        # This currently rasies an error from App Engine, should we raise our own?
        self.assertRaises(Exception, list, query)
        # Check that it's ok with PKs though
        query = TestUser.objects.filter(pk__in=list(xrange(1, 32)))
        list(query)

class BlobstoreFileUploadHandlerTest(TestCase):
    boundary = "===============7417945581544019063=="

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.META = {
            'wsgi.input': self._create_wsgi_input(),
            'content-type': 'message/external-body; blob-key="PLOF0qOie14jzHWJXEa9HA=="; access-type="X-AppEngine-BlobKey"'
        }
        self.uploader = BlobstoreFileUploadHandler(self.request)

    def _create_wsgi_input(self):
        return StringIO('--===============7417945581544019063==\r\nContent-Type:'
                        ' text/plain\r\nContent-Disposition: form-data;'
                        ' name="field-nationality"\r\n\r\nAS\r\n'
                        '--===============7417945581544019063==\r\nContent-Type:'
                        ' message/external-body; blob-key="PLOF0qOie14jzHWJXEa9HA==";'
                        ' access-type="X-AppEngine-BlobKey"\r\nContent-Disposition:'
                        ' form-data; name="field-file";'
                        ' filename="Scan.tiff"\r\n\r\nContent-Type: image/tiff'
                        '\r\nContent-Length: 19837164\r\nContent-MD5:'
                        ' YjI1M2Q5NjM5YzdlMzUxYjMyMjA0ZTIxZjAyNzdiM2Q=\r\ncontent-disposition:'
                        ' form-data; name="field-file";'
                        ' filename="Scan.tiff"\r\nX-AppEngine-Upload-Creation: 2014-03-07'
                        ' 14:48:03.246607\r\n\r\n\r\n'
                        '--===============7417945581544019063==\r\nContent-Type:'
                        ' text/plain\r\nContent-Disposition: form-data;'
                        ' name="field-number"\r\n\r\n6\r\n'
                        '--===============7417945581544019063==\r\nContent-Type:'
                        ' text/plain\r\nContent-Disposition: form-data;'
                        ' name="field-salutation"\r\n\r\nmrs\r\n'
                        '--===============7417945581544019063==--')

    def test_non_existing_files_do_not_get_created(self):
        file_field_name = 'field-file'
        length = len(self._create_wsgi_input().read())
        self.uploader.handle_raw_input(self.request.META['wsgi.input'], self.request.META, length, self.boundary, "utf-8")
        self.assertRaises(StopFutureHandlers, self.uploader.new_file, file_field_name, 'file_name', None, None)
        self.assertRaises(EntityNotFoundError, self.uploader.file_complete, None)

    def test_blob_key_creation(self):
        file_field_name = 'field-file'
        length = len(self._create_wsgi_input().read())
        self.uploader.handle_raw_input(self.request.META['wsgi.input'], self.request.META, length, self.boundary, "utf-8")
        self.assertRaises(
            StopFutureHandlers,
            self.uploader.new_file, file_field_name, 'file_name', None, None
        )
        self.assertIsNotNone(self.uploader.blobkey)
