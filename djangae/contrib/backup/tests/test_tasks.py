import json

from django.test import override_settings
from django.contrib.admin.models import LogEntry

from djangae.contrib.gauth_datastore.models import GaeDatastoreUser
from djangae.contrib import sleuth
from djangae.environment import application_id
from djangae.test import TestCase

from djangae.contrib.backup.tasks import (
    _get_valid_export_models,
    backup_datastore,
    SERVICE_URL
)

from google.appengine.api import app_identity


def mock_get_app_models(**kwargs):
    return [
        LogEntry,
        GaeDatastoreUser,
    ]


class GetValidExportModelsTestCase(TestCase):
    """Tests focused on djangae.contrib.backup.tasks._get_valid_export_models"""

    @override_settings(DJANGAE_BACKUP_EXCLUDE_MODELS=['django_admin_log'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_models_filtered(self):
        valid_models = _get_valid_export_models(
            ['django_admin_log', 'gauth_datastore_gaedatastoreuser']
        )
        self.assertNotIn('django_admin_log', valid_models)
        self.assertIn('gauth_datastore_gaedatastoreuser', valid_models)

    @override_settings(DJANGAE_BACKUP_EXCLUDE_APPS=['django'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_apps_filtered(self):
        valid_models = _get_valid_export_models(
            ['django_admin_log', 'gauth_datastore_gaedatastoreuser']
        )
        self.assertIn('gauth_datastore_gaedatastoreuser', valid_models)
        self.assertNotIn('django_admin_log', valid_models)


class BackupDatastoreTestCase(TestCase):
    """Tests for djangae.contrib.backup.tasks.backup_datastore"""

    @override_settings(DJANGAE_BACKUP_ENABLED=True)
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_ok(self):
        kinds = ['admin_logentry', 'gauth_datastore_gaedatastoreuser']
        with sleuth.watch('djangae.contrib.backup.tasks.urlfetch.fetch') as mock_fn:
            backup_datastore(kinds)

        self.assertTrue(mock_fn.called)
        call_args = mock_fn.calls[0][1]
        self.assertEqual(
            call_args['url'],
            SERVICE_URL.format(app_id=application_id())
        )
        self.assertItemsEqual(json.loads(call_args['payload'])['entity_filter']['kinds'], kinds)
        self.assertEqual(json.loads(call_args['payload'])['project_id'], application_id())

    @override_settings(DJANGAE_BACKUP_ENABLED=True)
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_invalid_kinds(self):
        kinds = ['not_real_model']
        with sleuth.watch('djangae.contrib.backup.tasks.urlfetch.fetch') as mock_fn:
            backup_datastore(kinds=kinds)

        self.assertFalse(mock_fn.called)

