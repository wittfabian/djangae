"""
    The gcloud SDK for Cloud Spanner doesn't work on the standard App Engine environment
    so our only option is to use the REST API. This file contains a simple client wrapper
    around the REST API.
"""

import json
import string
import threading

try:
    import six
except ImportError:
    from django.utils import six

from google.appengine.api import app_identity
from google.appengine.api import urlfetch
from google.appengine.api import oauth

from exceptions import StandardError


class Error(StandardError):
    pass


class DatabaseError(Error):
    pass


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


class InterfaceError(Error):
    pass


ENDPOINT_PREFIX = "https://spanner.googleapis.com/v1/"
ENDPOINT_SESSION_CREATE = (
    ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/sessions"
)

ENDPOINT_SQL_EXECUTE = (
    ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/sessions/{sid}:executeSql"
)


class Cursor(object):
    arraysize = 100

    def __init__(self, connection):
        self.connection = connection
        self.session = connection._create_session()

    def _format_query(self, sql, params):
        """
            Frustratingly, Cloud Spanner doesn't allow positional
            arguments in the SQL query, instead you need to specify
            named parameters (e.g. @msg_id) and params must be a dictionary.
            On top of that, there is another params structure for specifying the
            types of each parameter to avoid ambiguity (e.g. between bytes and string)

            This function takes the sql, and a list of params, and converts
            "%s" to "@a, "@b" etc. and returns a tuple of (sql, params, types)
            ready to be send via the REST API
        """

        output_params = {}
        param_types = {}

        for i, val in enumerate(params):
            letter = string.letters[i]
            output_params[letter] = val

            # Replace the next %s with a placeholder
            placeholder = "@{}".format(letter)
            sql = sql.replace("%s", placeholder, 1)

            if isinstance(val, six.unicode_type):
                param_types[letter] = "STRING"
            elif isinstance(val, six.bytes_type):
                param_types[letter] = "BYTES"

        return sql, output_params, param_types


    def execute(self, sql, params):
        sql, params, types = self._format_query(sql, params)

        data = {
            "session": self.session,
            "transaction": None,
            "sql": sql
        }

        if params:
            data.update({
                "params": params,
                "paramTypes": types
            })

        url_params = self.connection.url_params()
        url_params["sid"] = self.session
        response = self.connection._send_request(
            ENDPOINT_SQL_EXECUTE.format(**url_params),
            data
        )

        print(response)
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

    def close(self):
        self.connection._destroy_session(self.session)
        self.session = None


class Connection(object):
    def __init__(self, project_id, instance_id, database_id, auth_token):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.auth_token = auth_token
        self._autocommit = False

    def url_params(self):
        return {
            "pid": self.project_id,
            "iid": self.instance_id,
            "did": self.database_id
        }

    def _create_session(self):
        params = self.url_params()
        response = self._send_request(
            ENDPOINT_SESSION_CREATE.format(**params), {}
        )

        # For some bizarre reason, this returns the full URL to the session
        # so we just extract the session ID here!
        return response["name"].rsplit("/")[-1]

    def _destroy_session(self, session_id):
        pass

    def _send_request(self, url, data, method="POST"):
        payload = json.dumps(data) if data else None
        response = urlfetch.fetch(
            url,
            payload=payload,
            method=urlfetch.POST if method == "POST" else urlfetch.GET,
            headers={
                'Authorization': 'Bearer {}'.format(self.auth_token),
                'Content-Type': 'application/json'
            }
        )
        if not str(response.status_code).startswith("2"):
            raise DatabaseError("Error sending database request: {}".format(response.content))

        return json.loads(response.content)

    def autocommit(self, value):
        """
            Cloud Spanner doesn't support auto-commit, so if it's enabled we create
            and commit a read-write transaction for each query.
        """
        self._autocommit = value

    def cursor(self):
        return Cursor(self)

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


def connect(project_id, instance_id, database_id, credentials_json=None):
    if not credentials_json:
        auth_token, _ = app_identity.get_access_token(
            'https://www.googleapis.com/auth/cloud-platform'
        )
    else:
        from oauth2client.client import GoogleCredentials
        credentials = GoogleCredentials.from_stream(credentials_json)
        credentials = credentials.create_scoped('https://www.googleapis.com/auth/cloud-platform')
        access_token_info = credentials.get_access_token()
        auth_token = access_token_info.access_token

    return Connection(
        project_id, instance_id, database_id, auth_token
    )

