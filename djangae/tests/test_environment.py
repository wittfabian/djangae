import os

from djangae.tasks.deferred import defer
from djangae.environment import task_only, is_development_environment, is_production_environment
from djangae.test import TestCase
from djangae.contrib import sleuth
from django.http import HttpResponse


class TaskOnlyTestCase(TestCase):
    """ Tests for the @task_only decorator. """

    def test_403_if_not_task_or_admin(self):
        # If we are neither in a task or logged in as an admin, we expect a 403 response

        @task_only
        def view(request):
            return HttpResponse("Hello")

        response = view(None)
        self.assertEqual(response.status_code, 403)

    def test_allowed_if_in_task(self):
        """ If we're in an App Engine task then it should allow the request through. """

        @task_only
        def view(request):
            return HttpResponse("Hello")

        with sleuth.fake("djangae.environment.is_in_task", True):
            response = view(None)
        self.assertEqual(response.status_code, 200)

    def test_allowed_if_in_cron(self):
        """ If the view is being called by the GAE cron, then it should allow the request through. """

        @task_only
        def view(request):
            return HttpResponse("Hello")

        with sleuth.fake("djangae.environment.is_in_cron", True):
            response = view(None)
        self.assertEqual(response.status_code, 200)


class EnvironmentUtilsTest(TestCase):
    def test_is_production_environment(self):
        self.assertFalse(is_production_environment())
        os.environ["GAE_ENV"] = 'standard'
        self.assertTrue(is_production_environment())
        del os.environ["GAE_ENV"]

    def test_is_development_environment(self):
        self.assertTrue(is_development_environment())
        os.environ["GAE_ENV"] = 'standard'
        self.assertFalse(is_development_environment())
        del os.environ["GAE_ENV"]


def deferred_func():
    assert("HTTP_X_APPENGINE_TASKNAME" in os.environ)
    assert("HTTP_X_APPENGINE_QUEUENAME" in os.environ)
    assert("HTTP_X_APPENGINE_TASKEXECUTIONCOUNT" in os.environ)

    # Deferred tasks aren't cron tasks, so shouldn't have this header
    assert("HTTP_X_APPENGINE_CRON" not in os.environ)


class TaskHeaderTest(TestCase):

    def test_task_headers_are_available_in_tests(self):
        defer(deferred_func)
        self.process_task_queues()

        # Check nothing lingers
        self.assertFalse("HTTP_X_APPENGINE_TASKNAME" in os.environ)
        self.assertFalse("HTTP_X_APPENGINE_QUEUENAME" in os.environ)
        self.assertFalse("HTTP_X_APPENGINE_TASKEXECUTIONCOUNT" in os.environ)
