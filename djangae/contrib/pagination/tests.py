from django.db import models
from djangae.test import TestCase

from djangae.contrib.pagination import (
    paginated_model,
    DatastorePaginator,
    PaginationOrderingRequired
)

@paginated_model(orderings=[
    ("first_name",),
    ("last_name",),
    ("first_name", "last_name"),
    ("first_name", "-last_name")
])
class TestUser(models.Model):
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)

    def __unicode__(self):
        return u" ".join(self.first_name, self.last_name)

class PaginatedModelTests(TestCase):
    def test_fields_added_correctly(self):
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_last_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name_last_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name_neg_last_name"))


    def test_precalculate_field_values(self):
        user = TestUser.objects.create(pk=1, first_name="Luke", last_name="Benstead")

        self.assertEqual(u"Luke\x001", user.pagination_first_name)
        self.assertEqual(u"Benstead\x001", user.pagination_last_name)
        self.assertEqual(u"Luke\x00Benstead\x001", user.pagination_first_name_last_name)

        reversed_last_name = "".join([ unichr(0xffff - ord(x)) for x in "Benstead" ])

        self.assertEqual(u"Luke\x00{}\x001".format(reversed_last_name), user.pagination_first_name_neg_last_name)


class DatastorePaginatorTests(TestCase):
    def setUp(self):
        super(DatastorePaginatorTests, self).setUp()

        self.u1 = TestUser.objects.create(id=1, first_name="A", last_name="A")
        self.u2 = TestUser.objects.create(id=2, first_name="A", last_name="B")
        self.u3 = TestUser.objects.create(id=3, first_name="B", last_name="A")
        self.u4 = TestUser.objects.create(id=4, first_name="B", last_name="B")

    def test_pages_correct(self):
        paginator = DatastorePaginator(TestUser.objects.all().order_by("first_name"), 1) # 1 item per page

        self.assertEqual("A", paginator.page(1).object_list[0].first_name)
        self.assertEqual("A", paginator.page(2).object_list[0].first_name)
        self.assertEqual("B", paginator.page(3).object_list[0].first_name)
        self.assertEqual("B", paginator.page(4).object_list[0].first_name)

        paginator = DatastorePaginator(TestUser.objects.all().order_by("first_name", "last_name"), 1) # 1 item per page
        self.assertEqual(self.u1, paginator.page(1).object_list[0])
        self.assertEqual(self.u2, paginator.page(2).object_list[0])
        self.assertEqual(self.u3, paginator.page(3).object_list[0])
        self.assertEqual(self.u4, paginator.page(4).object_list[0])

        paginator = DatastorePaginator(TestUser.objects.all().order_by("first_name", "-last_name"), 1) # 1 item per page
        self.assertEqual(self.u2, paginator.page(1).object_list[0])
        self.assertEqual(self.u1, paginator.page(2).object_list[0])
        self.assertEqual(self.u4, paginator.page(3).object_list[0])
        self.assertEqual(self.u3, paginator.page(4).object_list[0])

        paginator = DatastorePaginator(TestUser.objects.all().order_by("-first_name"), 1) # 1 item per page
        self.assertEqual(self.u4, paginator.page(1).object_list[0])
        self.assertEqual(self.u3, paginator.page(2).object_list[0])
        self.assertEqual(self.u2, paginator.page(3).object_list[0])
        self.assertEqual(self.u1, paginator.page(4).object_list[0])

        with self.assertRaises(PaginationOrderingRequired):
            paginator = DatastorePaginator(TestUser.objects.all().order_by("-first_name", "last_name"), 1) # 1 item per page
            list(paginator.page(1).object_list)
