from django.conf import settings
from djangae.test import TestCase

from ..utils import get_datastore_setting


class GetDatastoreSettingTest(TestCase):
    def test_set_as_expected(self):
        with self.settings(DJANGAE_BACKUP_FOO=True):
            self.assertTrue(
                get_datastore_setting('FOO')
            )

    def test_default(self):
        self.assertFalse(hasattr(settings, 'FOO'))
        self.assertEqual(
            get_datastore_setting('FOO', required=False, default='bar'),
            'bar'
        )

    def test_not_required(self):
        """if a settings isnt required then return None"""
        self.assertFalse(hasattr(settings, 'FOO'))
        self.assertIsNone(
            get_datastore_setting('FOO', required=False),
        )

    def test_required_when_settings_does_not_exist(self):
        with self.assertRaises(Exception):
            get_datastore_setting('FOO')
