"""
    The gcloud SDK for Cloud Spanner doesn't work on the standard App Engine environment
    so our only option is to use the REST API. This file contains a simple client wrapper
    around the REST API.
"""

import json

from google.appengine.api import app_identity
from google.appengine.api import urlfetch

from exceptions import StandardError


class Error(StandardError):
    pass


class DatabaseError(Error):
    pass


class Cursor(object):
    arraysize = 100

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params):
        pass

    def executemany(self, sql, seq_of_params):
        pass

    def fetchone(self):
        pass

    def fetchmany(self, size=None):
        size = size or Cursor.arraysize

        pass

    def fetchall(self):
        pass


class Connection(object):
    def __init__(self, instance_id, database_id, auth_token):
        self.instance_id = instance_id
        self.database_id = database_id
        self.auth_token = auth_token

    def _send_request(self, url, data, method="POST"):
        response = urlfetch.fetch(
            url,
            method=urlfetch.POST if method == "POST" else urlfetch.GET,
            headers={
                'Authorization': 'Bearer {}'.format(self.auth_token)
            }
        )

        if not str(response.status_code).startswith("2"):
            raise DatabaseError("Error sending database request")

        return json.loads(response.content)

    def cursor(self):
        return Cursor(self)

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


def connect(instance_id, database_id):
    auth_token, _ = app_identity.get_access_token(
        'https://www.googleapis.com/auth/cloud-platform'
    )

    return Connection(
        instance_id, database_id, auth_token
    )

