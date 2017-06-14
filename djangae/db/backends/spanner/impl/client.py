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
ENDPOINT_SESSION_PREFIX = ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/sessions/{sid}"

ENDPOINT_SESSION_CREATE = (
    ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/sessions"
)

ENDPOINT_SQL_EXECUTE = ENDPOINT_SESSION_PREFIX + ":executeSql"
ENDPOINT_COMMIT = ENDPOINT_SESSION_PREFIX + ":commit"
ENDPOINT_UPDATE_DDL = ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/ddl"

class QueryType:
    DDL = "DDL"
    READ = "READ"
    WRITE = "WRITE"
    
    
def _determine_query_type(sql):
    for keyword in ("DATABASE", "TABLE", "INDEX"):
        if keyword in sql:
            return QueryType.DDL
            
    for keyword in ("INSERT", "UPDATE", "REPLACE", "DELETE"):
        if keyword in sql:
            return QueryType.WRITE
            
    return QueryType.READ


class Cursor(object):
    arraysize = 100

    def __init__(self, connection):
        self.connection = connection
        self._last_response = None

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


    def execute(self, sql, params=None):
        params = None or []

        sql, params, types = self._format_query(sql, params)

        query_type = _determine_query_type(sql)
        if query_type == QueryType.DDL:
            self._last_response = self.connection._run_ddl_update(sql)
            
            print self.connection._send_request(
                "https://spanner.googleapis.com/v1/projects/djangae-cloud/instances/spanner-test/databases/spanner-test/operations", None, method="GET"
            )
        else:
            self._last_response = self.connection._run_query(sql, params, types)

    def executemany(self, sql, seq_of_params):
        pass

    def fetchone(self):
        pass

    def fetchmany(self, size=None):
        size = size or Cursor.arraysize

        pass

    def fetchall(self):
        for row in self._last_response.get("rows", []):
            yield row

    def close(self):
        pass

class Connection(object):
    def __init__(self, project_id, instance_id, database_id, auth_token):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.auth_token = auth_token
        self._autocommit = False
        self._transaction_id = None
        self._session = self._create_session()

    def url_params(self):
        return {
            "pid": self.project_id,
            "iid": self.instance_id,
            "did": self.database_id,
            "sid": getattr(self, "_session", None) # won't exist when creating a session
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

    def _run_ddl_update(self, sql):
        print(sql)
        assert(_determine_query_type(sql) == QueryType.DDL)
    
        data = {
            "statements": [sql],
            "operationId": "test"
        }
    
        url_params = self.url_params()

        return self._send_request(
            ENDPOINT_UPDATE_DDL.format(**url_params),
            data,
            method="PATCH"
        )

    def _run_query(self, sql, params, types):
        print(sql)
        
        data = {
            "session": self._session,
            "transaction": self._transaction_id,
            "sql": sql
        }

        if params:
            data.update({
                "params": params,
                "paramTypes": types
            })

        # If we're running a query, with no active transaction then start a transaction
        # as part of this query. We use readWrite if it's an INSERT or UPDATE or CREATE or whatever
        if not self._transaction_id:
            query_type = _determine_query_type(data["sql"])
       
            transaction_type = (
                "readOnly" if query_type == QueryType.READ else "readWrite"
            )
            
            # Begin a transaction as part of this query if we are autocommitting
            data["transaction"] = {"begin": {transaction_type: {}}}

        url_params = self.url_params()
        
        result = self._send_request(
            ENDPOINT_SQL_EXECUTE.format(**url_params),
            data
        )

        transaction_id = result.get("transaction", {}).get("id")
        
        if transaction_id:
            # Keep the current transaction id active
            self._transaction_id = transaction_id

        # If auto-commit is enabled, then commit the active transaction
        if self.autocommit:
            self.commit()

        return result
    

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
        self._destroy_session(self._session)
        self._session = None

    def commit(self):
        if not self._transaction_id:
            return

        self._send_request(ENDPOINT_COMMIT, {"transactionId": self._transaction_id})
        self._transaction_id = None

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

