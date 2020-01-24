import contextlib
import os

from django import test

from djangae.environment import get_application_root
from djangae.tasks.test import (
    TaskFailedBehaviour,
    TaskFailedError,
    TestCaseMixin,
)
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


@contextlib.contextmanager
def environ_override(**kwargs):
    original = os.environ.copy()
    os.environ.update(kwargs)

    yield

    # Delete any keys that were introduced in kwargs
    for key in kwargs:
        if key not in original:
            del os.environ[key]

    # Restore original values
    os.environ.update(original)


class HandlerAssertionsMixin(object):
    """
    Custom assert methods which verifies a range of handler configuration
    setting specified in app.yaml.
    """

    msg_prefix = 'Handler configuration for {url} is not protected by {perm}.'

    def assert_login_admin(self, url):
        """
        Test that the handler defined in app.yaml which matches the url provided
        has `login: admin` in the configuration.
        """
        handler = self._match_handler(url)
        self.assertEqual(
            handler.url_map.login, appinfo.LOGIN_ADMIN, self.msg_prefix.format(
                url=url, perm='`login: admin`'
            )
        )

    def assert_login_required(self, url):
        """
        Test that the handler defined in app.yaml which matches the url provided
        has `login: required` or `login: admin` in the configruation.
        """
        handler = self._match_handler(url)
        login_admin = handler.url_map.login == appinfo.LOGIN_ADMIN
        login_required = handler.url_map.login == appinfo.LOGIN_REQUIRED or login_admin

        self.assertTrue(login_required, self.msg_prefix.format(
                url=url, perm='`login: admin` or `login: required`'
            )
        )

    def _match_handler(self, url):
        """
        Load script handler configurations from app.yaml and try to match
        the provided url path to a url_maps regex.
        """
        app_yaml_path = os.path.join(get_application_root(), "app.yaml")
        config = ModuleConfiguration(app_yaml_path)

        url_maps = config.handlers
        script_handlers = [
            _ScriptHandler(maps) for
            maps in url_maps if
            maps.GetHandlerType() == appinfo.HANDLER_SCRIPT
        ]

        for handler in script_handlers:
            if handler.match(url):
                return handler

        raise AssertionError('No handler found for {url}'.format(url=url))


class TestEnvironmentMixin(object):
    def setUp(self):
        enable_test_environment_variables()
        cache.clear()
        super().setUp()


class TestCase(HandlerAssertionsMixin, TestEnvironmentMixin, TestCaseMixin, test.TestCase):
    pass


class TransactionTestCase(HandlerAssertionsMixin, TestEnvironmentMixin, TestCaseMixin, test.TransactionTestCase):
    pass
