from django.db import models
from djangae.test import TestCase
from djangae.contrib.pagination import paginated_model

@paginated_model(orderings=[
    ("first_name",),
    ("last_name",),
    ("first_name", "last_name"),
    ("first_name", "-last_name")
])
class TestUser(models.Model):
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)


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
