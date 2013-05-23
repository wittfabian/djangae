import logging
import sys
import traceback
import os

from django.core.management.commands.syncdb import Command as OrigSyncDB
from django.db import connections

class Command(OrigSyncDB):

    def handle_noargs(self, **options):
        db = options.get('database')
        connection = connections[db]

        using_datastore = False
        if connection.__module__.split(".")[-2] == "datastore":
            from djangae.boot import find_project_root, application_id, data_root

            using_datastore = True

            from google.appengine.datastore import datastore_stub_util
            from google.appengine.datastore import datastore_sqlite_stub
            from google.appengine.api import apiproxy_stub_map

            datastore_stub = datastore_sqlite_stub.DatastoreSqliteStub(
                "dev~" + application_id(),
                os.path.join(data_root(), 'datastore.db'),
                False,
                trusted=False,
                root_path=find_project_root(),
                auto_id_policy=datastore_stub_util.SCATTERED
            )

            datastore_stub.SetConsistencyPolicy(datastore_stub_util.PseudoRandomHRConsistencyPolicy())
            apiproxy_stub_map.apiproxy.ReplaceStub('datastore_v3', datastore_stub)

        try:
            super(Command, self).handle_noargs(**options)
        finally:
            if using_datastore:
                pass
                #dev_appserver.TearDownStubs()

