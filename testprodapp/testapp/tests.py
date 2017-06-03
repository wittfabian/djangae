import uuid

from django.test import TestCase

from .models import Uuid


class UuidTest(TestCase):

    def setUp(self):
        Uuid.objects.create()
        self.uuid = Uuid.objects.get()

    def test_valid_data(self):
        self.assertIsNotNone(self.uuid.value)
        self.assertEqual(len(self.uuid.value), 36)
        uuid.UUID(self.uuid.value)


class UuidManagerTest(TestCase):

    def setUp(self):
        self.median_uuid = Uuid.objects.create_entities()

    def test_median_is_middle_value(self):
        self.assertEqual(Uuid.objects.count(), 1000)
        self.assertEqual(
            Uuid.objects.filter(value__lt=self.median_uuid).count(),
            500,
            )
