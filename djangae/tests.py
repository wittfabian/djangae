import datetime

from cStringIO import StringIO
from django.core.files.uploadhandler import StopFutureHandlers
from django.test import TestCase, RequestFactory
from django.db import models

from djangae.indexing import add_special_index

from .storage import BlobstoreFileUploadHandler
from google.appengine.api.datastore_errors import EntityNotFoundError
from django.db import IntegrityError

class User(models.Model):
    username = models.CharField(max_length=32)
    email = models.EmailField()
    last_login = models.DateField()

    def __unicode__(self):
        return self.username

class Permission(models.Model):
    user = models.ForeignKey(User)
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


class EdgeCaseTests(TestCase):
    def setUp(self):
        add_special_index(User, "username", "iexact")

        self.u1 = User.objects.create(username="A", email="test@example.com", last_login=datetime.datetime.now().date())
        self.u2 = User.objects.create(username="B", email="test@example.com", last_login=datetime.datetime.now().date())
        User.objects.create(username="C", email="test2@example.com", last_login=datetime.datetime.now().date())
        User.objects.create(username="D", email="test3@example.com", last_login=datetime.datetime.now().date())
        User.objects.create(username="E", email="test3@example.com", last_login=datetime.datetime.now().date())

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
        results = User.objects.filter(id__exact=self.u1.pk).filter(id__exact=self.u2.pk)
        self.assertEqual(list(results), [])

    def test_unusual_queries(self):
        results = User.objects.all()
        self.assertEqual(5, len(results))

        results = User.objects.filter(username__in=["A", "B"])
        self.assertEqual(2, len(results))
        self.assertItemsEqual(["A", "B"], [x.username for x in results])

        results = User.objects.filter(username__in=["A", "B"]).exclude(username="A")
        self.assertEqual(1, len(results), results)
        self.assertItemsEqual(["B"], [x.username for x in results])

        results = User.objects.filter(username__lt="E")
        self.assertEqual(4, len(results))
        self.assertItemsEqual(["A", "B", "C", "D"], [x.username for x in results])

        results = User.objects.filter(username__lte="E")
        self.assertEqual(5, len(results))

        #Double exclude not supported
        with self.assertRaises(RuntimeError):
            list(User.objects.exclude(username="E").exclude(username="A"))

        results = User.objects.filter(username="A", email="test@example.com")
        self.assertEqual(1, len(results))

    def test_counts(self):
        self.assertEqual(5, User.objects.count())
        self.assertEqual(2, User.objects.filter(email="test3@example.com").count())
        self.assertEqual(3, User.objects.exclude(email="test3@example.com").count())
        self.assertEqual(1,
            User.objects.filter(username="A").exclude(email="test3@example.com").count())

        with self.assertRaises(RuntimeError):
            list(User.objects.exclude(username="E").exclude(username="A"))


    def test_deletion(self):
        count = User.objects.count()

        self.assertTrue(count)

        User.objects.filter(username="A").delete()

        self.assertEqual(count - 1, User.objects.count())

        User.objects.filter(username="B").exclude(username="B").delete() #Should do nothing

        self.assertEqual(count - 1, User.objects.count())

        User.objects.all().delete()

        count = User.objects.count()

        self.assertFalse(count)

    def test_insert_with_existing_key(self):
        user = User.objects.create(id=1, username="test1", last_login=datetime.datetime.now().date())
        self.assertEqual(1, user.pk)

        with self.assertRaises(IntegrityError):
            User.objects.create(id=1, username="test2", last_login=datetime.datetime.now().date())

    def test_select_related(self):
        """ select_related should be a no-op... for now """
        user = User.objects.get(username="A")
        perm = Permission.objects.create(user=user, perm="test_perm")
        select_related = [ (p.perm, p.user.username) for p in user.permission_set.select_related() ]
        self.assertEqual(user.username, select_related[0][1])

    def test_cross_selects(self):
        user = User.objects.get(username="A")
        perm = Permission.objects.create(user=user, perm="test_perm")
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
            list(User.objects.all().values_list('pk', flat=True))
        finally:
            Query.__init__ = original_init

        self.assertTrue(replacement_init.called_kwargs.get('keys_only'))
        self.assertEqual(5, len(User.objects.all().values_list('pk')))

    def test_iexact(self):
        user = User.objects.get(username__iexact="a")
        self.assertEqual("A", user.username)

    def test_ordering(self):
        users = User.objects.all().order_by("username")

        self.assertEqual(["A", "B", "C", "D", "E"], [x.username for x in users])

        users = User.objects.all().order_by("-username")

        self.assertEqual(["A", "B", "C", "D", "E"][::-1], [x.username for x in users])

    def test_dates_query(self):
        User.objects.create(username="Z", email="z@example.com", last_login=datetime.date(2013, 4, 5))

        last_a_login = User.objects.get(username="A").last_login

        dates = User.objects.dates('last_login', 'year')
        self.assertItemsEqual(
            [datetime.datetime(2013, 1, 1, 0, 0), datetime.datetime(last_a_login.year, 1, 1, 0, 0)],
            dates
        )

        dates = User.objects.dates('last_login', 'month')
        self.assertItemsEqual(
            [datetime.datetime(2013, 4, 1, 0, 0), datetime.datetime(last_a_login.year, last_a_login.month, 1, 0, 0)],
            dates
        )

        dates = User.objects.dates('last_login', 'day')
        self.assertItemsEqual(
            [datetime.datetime(2013, 4, 5, 0, 0), datetime.datetime.combine(last_a_login, datetime.datetime.min.time())],
            dates
        )

        dates = User.objects.dates('last_login', 'day', order='DESC')
        self.assertItemsEqual(
            [datetime.datetime.combine(last_a_login, datetime.datetime.min.time()), datetime.datetime(2013, 4, 5, 0, 0)],
            dates
        )

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
