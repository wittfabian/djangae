# STANDARD LIB
import mock

# LIBRARIES
from django.test import TestCase

# DJANGAE
from .middleware import override_default_kwargs, check_url_kwarg_for_http


class MiddlewarePatchesTest(TestCase):

    def test_override_default_kwargs(self):
        """ Test the `override_default_kwargs` decorator. """

        @override_default_kwargs(c=7)
        def my_func(a, b=1, c=2):
            return ",".join(str(x) for x in [a,b,c])

        # Test that the default override works
        self.assertEqual(my_func(0), "0,1,7")
        # Test that we can still specify our own values for all kwargs if we want to
        self.assertEqual(my_func(0, b=3, c=5), "0,3,5")

    @mock.patch("djangae.contrib.security.middleware.logging.warn")
    def test_check_url_kwarg_for_http(self, logging_mock):
        def my_func(url="default"):
            return
        wrapped = check_url_kwarg_for_http(my_func)

        # Calling our original function should NOT do any logging
        my_func(url="http://insecure.com")
        self.assertFalse(logging_mock.called)
        # Calling the wrapped function but with https should NOT do any logging
        wrapped(url="https://secure.com")
        self.assertFalse(logging_mock.called)
        # Calling the wrapped function with http SHOULD log a warning
        wrapped(url="http://insecure.com")
        self.assertTrue(logging_mock.called)
