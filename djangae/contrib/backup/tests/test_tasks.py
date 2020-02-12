from django.test import override_settings
from django.contrib.admin.models import LogEntry
from django.db import models

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

    def test_models_using_the_same_table_only_listed_once(self):
        class ModelFoo(models.Model):
            class Meta:
                db_table = "foo"

        class ModelBar(models.Model):
            class Meta:
                db_table = "foo"

        def mock_get_app_models(**kwargs):
            return [ModelFoo, ModelBar]

        with sleuth.switch('django.apps.apps.get_models', mock_get_app_models):
            valid_models = _get_valid_export_kinds()
            self.assertEquals(['foo'], valid_models)

    @override_settings(DJANGAE_BACKUP_EXCLUDE_MODELS=['django_admin_log'])
    def test_kinds_are_deduplicated(self):
        valid_models = _get_valid_export_kinds(kinds=[
            'gauth_datastore_gaedatastoreuser',
            'gauth_datastore_gaedatastoreuser',
            'djangae_gaedatastoreuser',
            'djangae_gaedatastoreuser',
        ])
        self.assertEquals(['djangae_gaedatastoreuser'], valid_models)



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
