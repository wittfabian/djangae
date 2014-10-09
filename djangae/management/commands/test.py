import sys
from unittest import skip

from django.core.management.commands import test
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_by_path


class Command(test.Command):

    def handle(self, *args, **kwargs):

        # Look for the previous app in INSTALLED_APPS that defines a
        # test command for, eg., South support.

        apps = settings.INSTALLED_APPS[:]
        previous_apps = reversed(apps[:apps.index('djangae')])

        CommandClass = test.Command
        for app in previous_apps:
            try:
                CommandClass = import_by_path('{}.management.commands.test.Command'.format(app))
                break
            except ImproperlyConfigured:
                pass

        if settings.DATABASES['default']['ENGINE'] == 'djangae.db.backends.appengine':
            _monkey_patch_unsupported_tests()

        CommandClass().handle(*args, **kwargs)


def _monkey_patch_unsupported_tests():
    unsupported_tests = []

    if 'django.contrib.auth' in settings.INSTALLED_APPS:
        import django
        if django.VERSION[:2] == (1, 5):
            unsupported_tests.extend([
                #These auth tests override the AUTH_USER_MODEL setting, which then uses M2M joins
                'django.contrib.auth.tests.auth_backends.CustomPermissionsUserModelBackendTest.test_custom_perms',
                'django.contrib.auth.tests.auth_backends.CustomPermissionsUserModelBackendTest.test_get_all_superuser_permissions',
                'django.contrib.auth.tests.auth_backends.CustomPermissionsUserModelBackendTest.test_has_no_object_perm',
                'django.contrib.auth.tests.auth_backends.CustomPermissionsUserModelBackendTest.test_has_perm',
                'django.contrib.auth.tests.auth_backends.ExtensionUserModelBackendTest.test_custom_perms',
                'django.contrib.auth.tests.auth_backends.ExtensionUserModelBackendTest.test_has_perm',
                'django.contrib.auth.tests.auth_backends.ExtensionUserModelBackendTest.test_get_all_superuser_permissions',
                'django.contrib.auth.tests.auth_backends.ExtensionUserModelBackendTest.test_has_no_object_perm'
            ])

    for unsupported_test in unsupported_tests:
        module_path, klass_name, method_name = unsupported_test.rsplit(".", 2)

        __import__(module_path, klass_name)

        module = sys.modules[module_path]
        if hasattr(module, klass_name):
            klass = getattr(module, klass_name)
            method = getattr(klass, method_name)
            setattr(klass, method_name, skip("Not supported by Djangae")(method))
