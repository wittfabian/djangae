from django.test.simple import DjangoTestSuiteRunner

import unittest
from unittest import TextTestResult

from djangae.db.backends.appengine.dbapi import NotSupportedError, CouldBeSupportedError

class SkipUnsupportedTestResult(TextTestResult):

    def addError(self, test, err):
        if err[0] in (NotSupportedError, CouldBeSupportedError):
            self.addExpectedFailure(test, err)
        else:
            super(SkipUnsupportedTestResult, self).addError(test, err)

class DjangaeTestSuiteRunner(DjangoTestSuiteRunner):
    def run_suite(self, suite, **kwargs):
        return unittest.TextTestRunner(
            verbosity=self.verbosity,
            failfast=self.failfast,
            resultclass=SkipUnsupportedTestResult
        ).run(suite)
