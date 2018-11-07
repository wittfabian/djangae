import os

from djangae.contrib import sleuth
from djangae.test import TestCase

from django.contrib.admin.models import LogEntry
from djangae.contrib.gauth_datastore.models import (
    GaeDatastoreUser,
    Group,
)
from django.contrib.sites.models import Site

from ..views import (
    create_datastore_backup,
    GAE_BUILTIN_MODULE,
)


class DataStoreBackupTest(TestCase):
    def test_task_is_queued(self):
        models = [
            LogEntry,
            GaeDatastoreUser,
            Group,
            Site
        ]
        with sleuth.fake('django.apps.apps.get_models', models):
            bucket = 'testapp/19991231-235900'

            with sleuth.fake('djangae.contrib.backup.views.get_backup_path', bucket):
                with self.settings(
                        DJANGAE_BACKUP_ENABLED=True,
                        DJANGAE_BACKUP_GCS_BUCKET='testapp',
                        DJANGAE_BACKUP_NAME='testapp-bk',
                        DJANGAE_BACKUP_EXCLUDE_APPS=[
                            'sites'
                        ],
                        DJANGAE_BACKUP_EXCLUDE_MODELS=[
                            'gauth_datastore.Group'
                        ]):

                    try:
                        os.environ["HTTP_X_APPENGINE_CRON"] = "1"
                        create_datastore_backup(None)
                    finally:
                        del os.environ["HTTP_X_APPENGINE_CRON"]

        # assert task was triggered
        tasks = self.taskqueue_stub.get_filtered_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].target, GAE_BUILTIN_MODULE)
        self.assertEqual(tasks[0].url,
            '/_ah/datastore_admin/backup.create?'
            'name=testapp-bk'
            '&gs_bucket_name=testapp%2F19991231-235900'
            '&filesystem=gs'
            '&kind=django_admin_log'
            '&kind=djangae_gaedatastoreuser'
        )
