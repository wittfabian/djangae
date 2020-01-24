import os

from djangae.tasks.test import (
    TaskFailedBehaviour,
    TaskFailedError,
    TestCaseMixin,
)
from django import test
from django.core.cache import cache

TaskFailedError = TaskFailedError
TaskFailedBehaviour = TaskFailedBehaviour


def enable_test_environment_variables():
    """
        Sets up sample environment variables that are available on production
    """

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "example")
    os.environ.setdefault("GAE_APPLICATION", "e~example")
    os.environ.setdefault("GAE_ENV", "development")


class TestEnvironmentMixin(object):
    def setUp(self):
        enable_test_environment_variables()
        cache.clear()
        super().setUp()


class TestCase(TestEnvironmentMixin, TestCaseMixin, test.TestCase):
    pass


class TransactionTestCase(TestEnvironmentMixin, TestCaseMixin, test.TransactionTestCase):
    pass
