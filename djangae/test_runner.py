import unittest
import os
from unittest import TextTestResult

from django.test.simple import DjangoTestSuiteRunner

from django.db import NotSupportedError
from djangae.utils import find_project_root

from google.appengine.ext import testbed


# Many Django tests require saving instances with a PK
# of zero. App Engine doesn't allow this (it treats the key
# as incomplete in this case) so we skip those tests here
DJANGO_TESTS_WHICH_REQUIRE_ZERO_PKS = {
    'model_forms.tests.ModelMultipleChoiceFieldTests.test_model_multiple_choice_required_false',
    'model_forms.tests.ModelChoiceFieldTests.test_modelchoicefield',
    'custom_pk.tests.CustomPKTests.test_zero_non_autoincrement_pk',
    'bulk_create.tests.BulkCreateTests.test_zero_as_autoval'
}

# These tests only work if you haven't changed AUTH_USER_MODEL
# This is probably a bug in Django (the tests should use skipIfCustomUser)
# but I haven't had a chance to see if it's fixed in master (and it's not fixed in
# 1.7, so this needs to exist either way)
DJANGO_TESTS_WHICH_REQUIRE_AUTH_USER = {
    'proxy_models.tests.ProxyModelAdminTests.test_cascade_delete_proxy_model_admin_warning',
    'proxy_models.tests.ProxyModelAdminTests.test_delete_str_in_model_admin',
    'proxy_models.tests.ProxyModelTests.test_permissions_created' # Requires permissions created
}


DJANGO_TESTS_TO_SKIP = DJANGO_TESTS_WHICH_REQUIRE_ZERO_PKS.union(DJANGO_TESTS_WHICH_REQUIRE_AUTH_USER)

def init_testbed():
    # We don't initialize the datastore stub here, that needs to be done by Django's create_test_db and destroy_test_db.
    IGNORED_STUBS = [ "init_datastore_v3_stub" ]

    stub_kwargs = {
        "init_taskqueue_stub": {
            "root_path": find_project_root()
        }
    }
    bed = testbed.Testbed()
    bed.activate()
    for init_name in testbed.INIT_STUB_METHOD_NAMES.values():
        if init_name in IGNORED_STUBS:
            continue

        getattr(bed, init_name)(**stub_kwargs.get(init_name, {}))

    return bed


def bed_wrap(test):
    def _wrapped(*args, **kwargs):
        bed = None
        try:
            # Init test stubs
            bed = init_testbed()

            return test(*args, **kwargs)
        finally:
            if bed:
                bed.deactivate()
                bed = None

    return _wrapped


class SkipUnsupportedTestResult(TextTestResult):
    def addError(self, test, err):
        skip = os.environ.get("SKIP_UNSUPPORTED", True)
        if skip and err[0] in (NotSupportedError,):
            self.addExpectedFailure(test, err)
        else:
            super(SkipUnsupportedTestResult, self).addError(test, err)

class DjangaeTestSuiteRunner(DjangoTestSuiteRunner):
    def build_suite(self, *args, **kwargs):
        suite = super(DjangaeTestSuiteRunner, self).build_suite(*args, **kwargs)

        new_tests = []

        for i, test in enumerate(suite._tests):

            # https://docs.djangoproject.com/en/1.7/topics/testing/advanced/#django.test.TransactionTestCase.available_apps
            # available_apis is part of an internal API that allows to speed up
            # internal Django test,  but that breaks the integration with
            # Djangae models and tests, so we are disabling it here
            if hasattr(test, 'available_apps'):
                test.available_apps = None

            if test.id() in DJANGO_TESTS_TO_SKIP:
                continue #FIXME: It would be better to wrap this in skipTest or something

            new_tests.append(bed_wrap(test))

        suite._tests[:] = new_tests

        return suite


class SkipUnsupportedRunner(DjangaeTestSuiteRunner):
    def run_suite(self, suite, **kwargs):
        return unittest.TextTestRunner(
            verbosity=self.verbosity,
            failfast=self.failfast,
            resultclass=SkipUnsupportedTestResult
        ).run(suite)
