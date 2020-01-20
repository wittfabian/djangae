import json
from django.db import models
from django.test import override_settings
from django.contrib.admin.models import LogEntry

from djangae.contrib import sleuth
from djangae.environment import application_id
from djangae.test import TestCase

from djangae.contrib.backup.tasks import (
    _get_valid_export_models,
    backup_datastore,
    SERVICE_URL,
    AUTH_SCOPES,
)

from google.auth import app_engine


class MockUser(models.Model):
    class Meta:
        app_label = "backup"


def mock_get_app_models(**kwargs):
    return [
        LogEntry,
        MockUser,
    ]


class GetValidExportModelsTestCase(TestCase):
    """Tests focused on djangae.contrib.backup.tasks._get_valid_export_models"""

    @override_settings(DJANGAE_BACKUP_EXCLUDE_MODELS=['django_admin_log'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_models_filtered(self):
        valid_models = _get_valid_export_models(
            ['django_admin_log', 'backup_mockuser']
        )
        self.assertNotIn('django_admin_log', valid_models)
        self.assertIn('backup_mockuser', valid_models)

    @override_settings(DJANGAE_BACKUP_EXCLUDE_APPS=['django'])
    @sleuth.switch('django.apps.apps.get_models', mock_get_app_models)
    def test_apps_filtered(self):
        valid_models = _get_valid_export_models(
            ['django_admin_log', 'backup_mockuser']
        )
        self.assertIn('backup_mockuser', valid_models)
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
                kinds = ['backup_mockuser']
                backup_datastore(kinds=kinds)
                self.assertTrue(mock_fn.called)
