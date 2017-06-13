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
            with self.settings(
                    DS_BACKUP_ENABLED=True,
                    DS_BACKUP_GCS_BUCKET='testapp',
                    DS_BACKUP_NAME='testapp-bk',
                    DS_BACKUP_EXCLUDE_APPS=[
                        'sites'
                    ],
                    DS_BACKUP_EXCLUDE_MODELS=[
                        'gauth_datastore.Group'
                    ]):
                create_datastore_backup(None)

        # assert task was triggered
        tasks = self.taskqueue_stub.get_filtered_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].target, GAE_BUILTIN_MODULE)
        self.assertEqual(tasks[0].url,
            '/_ah/datastore_admin/backup.create?'
            'name=testapp-bk'
            '&amp;gs_bucket_name=testapp'
            '&amp;filesystem=gs'
            '&amp;kind=django_admin_log'
            '&amp;kind=djangae_gaedatastoreuser'
        )
