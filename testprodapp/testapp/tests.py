import uuid

from django.test import TestCase

from .models import TestResult
from .models import Uuid


class TestResultTest(TestCase):

    def setUp(self):
        self.result = TestResult.objects.create(name='test')

    def test_valid_data(self):
        self.assertIsNotNone(self.result.last_modified)
        self.assertEqual(self.result.status, 'new')
        self.assertEqual(self.result.output, '')


class TestResultManagerTest(TestCase):

    def setUp(self):
        self.result_id = TestResult.objects.create(name='test').id

    def test_getter(self):
        self.assertEqual(TestResult.objects.count(), 1)
        result = TestResult.objects.get_result('test')
        self.assertIsNotNone(result)
        self.assertEqual(result.id, self.result_id)

    def test_getter_new_name(self):
        TestResult.objects.get_result('test2')
        self.assertEqual(TestResult.objects.count(), 2)

    def test_setter(self):
        result = TestResult.objects.set_result('test', 'success', 'abc')
        self.assertEqual(TestResult.objects.count(), 1)
        self.assertIsNotNone(result)
        result = TestResult.objects.get_result('test')
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.output, 'abc')

    def test_setter_new_name(self):
        TestResult.objects.set_result('test2', 'success', 'abc')
        self.assertEqual(TestResult.objects.count(), 2)


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
