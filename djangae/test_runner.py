import unittest
from unittest import TextTestResult

from django.test.simple import DjangoTestSuiteRunner

from djangae.db.backends.appengine.dbapi import NotSupportedError, CouldBeSupportedError
from djangae.utils import find_project_root

from google.appengine.ext import testbed


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
        if err[0] in (NotSupportedError, CouldBeSupportedError):
            self.addExpectedFailure(test, err)
        else:
            super(SkipUnsupportedTestResult, self).addError(test, err)

class DjangaeTestSuiteRunner(DjangoTestSuiteRunner):
    def build_suite(self, *args, **kwargs):
        suite = super(DjangaeTestSuiteRunner, self).build_suite(*args, **kwargs)

        for i, test in enumerate(suite._tests):
            suite._tests[i] = bed_wrap(test)

        return suite


class SkipUnsupportedRunner(DjangaeTestSuiteRunner):
    def run_suite(self, suite, **kwargs):
        return unittest.TextTestRunner(
            verbosity=self.verbosity,
            failfast=self.failfast,
            resultclass=SkipUnsupportedTestResult
        ).run(suite)
