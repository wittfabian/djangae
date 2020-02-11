from django.test import override_settings
from django.contrib.admin.models import LogEntry

from djangae.contrib.gauth_datastore.models import GaeDatastoreUser
from djangae.contrib import sleuth
from djangae.test import TestCase

from djangae.contrib.backup.tasks import (
    _get_valid_export_kinds,
    backup_datastore,
    AUTH_SCOPES,
)

from google.auth import app_engine


def mock_get_app_models(**kwargs):
    return [
        LogEntry,
        GaeDatastoreUser,
    ]


class GetValidExportKindsTestCase(TestCase):
    """Tests focused on djangae.contrib.backup.tasks._get_valid_export_kinds"""

    @override_settings(DJANGAE_BACKUP_EXCLUDE_MODELS=['django_admin_log'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_models_filtered_by_model(self):
        valid_models = _get_valid_export_kinds(
            ['django_admin_log', 'gauth_datastore_gaedatastoreuser']
        )
        self.assertNotIn('django_admin_log', valid_models)
        self.assertIn('djangae_gaedatastoreuser', valid_models)

    @override_settings(DJANGAE_BACKUP_EXCLUDE_MODELS=['django_admin_log'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_models_filtered_by_kind(self):
        valid_models = _get_valid_export_kinds(
            ['django_admin_log', 'djangae_gaedatastoreuser']
        )
        self.assertNotIn('django_admin_log', valid_models)
        self.assertIn('djangae_gaedatastoreuser', valid_models)

    @override_settings(DJANGAE_BACKUP_EXCLUDE_APPS=['admin'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_apps_filtered(self):
        valid_models = _get_valid_export_kinds(
            ['django_admin_log', 'gauth_datastore_gaedatastoreuser']
        )
        self.assertIn('djangae_gaedatastoreuser', valid_models)
        self.assertNotIn('django_admin_log', valid_models)


class BackupTestCase(TestCase):

    @override_settings(DJANGAE_BACKUP_ENABLED=True)
    def test_ok(self):
        """Lightweight end-to-end flow test of backup_datastore."""
        with sleuth.switch(
            'djangae.contrib.backup.tasks._get_authentication_credentials',
            lambda: app_engine.Credentials(scopes=AUTH_SCOPES)
        ):
            with sleuth.switch(
                'googleapiclient.http.HttpRequest.execute', lambda x: True
            ) as mock_fn:
                kinds = ['gauth_datastore_gaedatastoreuser']
                backup_datastore(kinds=kinds)
                self.assertTrue(mock_fn.called)
