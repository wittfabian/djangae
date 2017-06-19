"""
    The gcloud SDK for Cloud Spanner doesn't work on the standard App Engine environment
    so our only option is to use the REST API. This file contains a simple client wrapper
    around the REST API.
"""

import json
import string
import time
import uuid
import datetime
import base64
import random

from pytz import utc


try:
    import six
except ImportError:
    from django.utils import six

from google.appengine.api import app_identity
from google.appengine.api import urlfetch

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
ENDPOINT_OPERATION_GET = ENDPOINT_PREFIX + "projects/{pid}/instances/{iid}/databases/{did}/operations/{oid}"
ENDPOINT_BEGIN_TRANSACTION = ENDPOINT_SESSION_PREFIX + ":beginTransaction"

class QueryType:
    DDL = "DDL"
    READ = "READ"
    WRITE = "WRITE"


def _determine_query_type(sql):
    if sql.strip().split()[0].upper() == "SELECT":
        return QueryType.READ

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
        self._iterator = None
        self._lastrowid = None

    @property
    def lastrowid(self):
        return self._lastrowid

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

            if isinstance(val, six.text_type):
                param_types[letter] = {"code": "STRING"}
            elif isinstance(val, six.binary_type):
                param_types[letter] = {"code": "BYTES"}
            elif isinstance(val, six.integer_types):
                param_types[letter] = {'code': 'INT64'}
                output_params[letter] = six.text_type(val)

        if params:
            print("%s - %s" % (output_params, param_types))
        return sql, output_params, param_types


    def execute(self, sql, params=None):
        params = params or []

        sql, params, types = self._format_query(sql, params)

        query_type = _determine_query_type(sql)
        if query_type == QueryType.DDL:
            self._last_response = self.connection._run_ddl_update(sql)
        else:
            self._last_response = self.connection._run_query(sql, params, types)
            self._iterator = iter(self._last_response.get("rows", []))

    def executemany(self, sql, seq_of_params):
        pass

    def fetchone(self):
        return self._iterator.next()

    def fetchmany(self, size=None):
        size = size or Cursor.arraysize
        results = []
        for i, result in enumerate(self._iterator):
            if i == size:
                return results
            results.append(result)
        return results

    def fetchall(self):
        for row in self._iterator:
            yield row

    def close(self):
        pass


class ParsedSQLInfo(object):
    def __init__(self, method, table, columns):
        self.method = method
        self.table = table
        self.columns = columns
        self.row_values = []

    def _add_row(self, values):
        self.row_values.append(values)


def _convert_for_json(values):
    """
        Cloud Spanner has a slightly bizarre system for sending different
        types (e.g. integers must be strings) so this takes care of converting
        Python types to the correct format for JSON
    """

    for i, value in enumerate(values):

        if isinstance(value, six.integer_types):
            values[i] = six.text_type(value) # Ints must be strings
        elif isinstance(value, six.binary_type):
            values[i] = base64.b64encode(value) # Bytes must be b64 encoded
        elif isinstance(value, datetime.datetime):
            # datetimes must send the Zulu (UTC) timezone...
            if value.tzinfo:
                value = value.astimezone(utc)
            values[i] = value.isoformat("T") + "Z"
        elif isinstance(value, datetime.date):
            values[i] = value.isoformat()
    return values


def parse_sql(sql, params):
    """
        Parses a restrictive subset of SQL for "write" queries (INSERT, UPDATE etc.)
    """

    parts = sql.split()

    method = parts[0].upper().strip()
    table = None
    columns = []

    rows = []

    if method == "INSERT":
        assert(parts[1].upper() == "INTO")
        table = parts[2]

        def parse_bracketed_list_from(start):
            bracketed_list = []
            for i in range(start, len(parts)):
                if parts[i].endswith(")"):
                    remainder = parts[i].rstrip(")").strip()
                    if remainder:
                        bracketed_list.append(remainder)
                    break

                remainder = parts[i].lstrip("(").strip()
                # Depending on whether there was whitespace before/after brackets/commas
                # remainder will either be a column, or a CSV of columns
                if "," in remainder:
                    bracketed_list.extend([x.strip() for x in remainder.split(",") if x.strip()])
                elif remainder:
                    bracketed_list.append(remainder)

            return bracketed_list, i

        columns, last = parse_bracketed_list_from(3)

        assert(parts[last + 1] == "VALUES")

        start = last + 2
        while start < len(parts):
            row, last = parse_bracketed_list_from(start)
            rows.append(row)
            start = last + 1

    else:
        raise NotImplementedError()

    # Remove any backtick quoting
    table = table.strip("`")
    columns = [x.strip("`") for x in columns]
    result = ParsedSQLInfo(method, table, columns)

    for value_list in rows:
        values = [params[x.strip("@")] for x in value_list]
        values = _convert_for_json(values)
        result._add_row(values)

    return result


class Connection(object):
    def __init__(self, project_id, instance_id, database_id, auth_token):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.auth_token = auth_token
        self._autocommit = False
        self._transaction_id = None
        self._transaction_mutations = []
        self._session = self._create_session()
        self._pk_lookup = self._query_pk_lookup()

        half_sixty_four = ((2 ** 64) - 1) / 2

        self._sequence_generator = lambda: (
            random.randint(
                -half_sixty_four,
                (half_sixty_four - 1)
            )
        )

    def _query_pk_lookup(self):
        sql = """
SELECT DISTINCT
  I.TABLE_NAME,
  IC.COLUMN_NAME
FROM
  information_schema.indexes AS I
INNER JOIN
  information_schema.index_columns as IC
on I.INDEX_NAME = IC.INDEX_NAME and I.TABLE_NAME = IC.TABLE_NAME
WHERE I.INDEX_TYPE = "PRIMARY_KEY"
AND IC.TABLE_SCHEMA = ''
""".strip()

        self.autocommit(True)
        results = self._run_query(sql, None, None)
        self.autocommit(False)

        return dict(results['rows'])

    def set_sequence_generator(self, func):
        self._sequence_generator = func

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

    def _parse_mutation(self, sql, params, types):
        """
            Spanner doesn't support insert/update/delete/replace etc. queries
            but it does support submitting "mutations" when a transaction is committed.

            This function parses out the following information from write queries:
             - table name
             - columns
             - values

            ...and returns a dictionary in the correct format for the mutations list
            in the commit() RPC call
        """

        parsed_output = parse_sql(sql, params)

        return {
            parsed_output.method.lower(): {
                "table": parsed_output.table,
                "columns": parsed_output.columns,
                "values": parsed_output.row_values
            }
        }

    def _generate_pk_for_insert(self, mutation):
        """
            If the mutation is an INSERT and the PK column is *NOT*
            included, we generate a new random ID and insert that and the PK
            column into the mutation.
        """
        if mutation.keys()[0] != "insert":
            # Do nothing if this isn't an insert
            return mutation

        m = mutation['insert']
        pk_column = self._pk_lookup[m['table']]
        if pk_column not in m['columns']:
            m['columns'].insert(0, pk_column)

            for row in m['values']:
                # INT64 must be sent as a string :(
                row.insert(0, six.text_type(self._sequence_generator()))

        return mutation

    def _destroy_session(self, session_id):
        pass

    def _run_ddl_update(self, sql, wait=True):
        print(sql)

        assert(_determine_query_type(sql) == QueryType.DDL)

        # Operation IDs must start with a letter
        operation_id = "x" + uuid.uuid4().hex.replace("-", "_")

        def split_sql_on_semi_colons(_sql):
            inside_quotes = False

            results = []
            buff = []

            for c in sql:
                if c in ("'", '"', "`"):
                    inside_quotes = not inside_quotes

                if c == ";" and not inside_quotes:
                    results.append("".join(buff))
                    buff = []
                else:
                    buff.append(c)

            if buff:
                results.append("".join(buff))

            return results

        data = {
            "statements": split_sql_on_semi_colons(sql),
            "operationId": operation_id
        }

        url_params = self.url_params()

        response = self._send_request(
            ENDPOINT_UPDATE_DDL.format(**url_params),
            data,
            method="PATCH"
        )

        if wait:
            # Wait for the operation to finish
            done = False
            params = url_params.copy()
            params["oid"] = operation_id
            while not done:
                status = self._send_request(
                    ENDPOINT_OPERATION_GET.format(**params), data=None, method="GET"
                )
                done = status.get("done", False)
                time.sleep(0.1)

        return response

    def _run_query(self, sql, params, types):
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

        query_type = _determine_query_type(data["sql"])

        # If we're running a query, with no active transaction then start a transaction
        # as part of this query. We use readWrite if it's an INSERT or UPDATE or CREATE or whatever
        if not self._transaction_id:
            if self._autocommit:
                # Autocommit means this is a single-use transaction, however passing singleUse
                # to executeSql is apparently illegal... for some reason?
                transaction_type = (
                    "readOnly" if query_type == QueryType.READ else "readWrite"
                )
            else:
                # If autocommit is disabled, we have to assume a readWrite transaction
                # as even if the query type is READ, subsequent queries within the transaction
                # may include UPDATEs
                transaction_type = "readWrite"

            # Begin a transaction as part of this query if we are autocommitting
            data["transaction"] = {"begin": {transaction_type: {}}}

        url_params = self.url_params()

        transaction_id = None
        if query_type == QueryType.READ:
            result = self._send_request(
                ENDPOINT_SQL_EXECUTE.format(**url_params),
                data
            )

            transaction_id = result.get("transaction", {}).get("id")
        else:
            if not self._transaction_id:
                # Start a new transaction, but store the mutation for the commit
                result = self._send_request(
                    ENDPOINT_BEGIN_TRANSACTION.format(**url_params),
                    {"options": {"readWrite": {}}}
                )

                transaction_id = result["id"]
            else:
                result = {}

            mutation = self._parse_mutation(sql, params, types)
            mutation = self._generate_pk_for_insert(mutation)

            self._transaction_mutations.append(mutation)

        if transaction_id:
            # Keep the current transaction id active
            self._transaction_id = transaction_id

        # If auto-commit is enabled, then commit the active transaction
        if self._autocommit:
            self.commit()

        return result


    def _send_request(self, url, data, method="POST"):
        def get_method():
            assert(method in ("GET", "POST", "PUT", "PATCH", "HEAD", "DELETE"))
            return getattr(urlfetch, method)

        payload = json.dumps(data) if data else None
        response = urlfetch.fetch(
            url,
            payload=payload,
            method=get_method(),
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

        print(self._transaction_mutations)

        self._send_request(
            ENDPOINT_COMMIT.format(**self.url_params()), {
                "transactionId": self._transaction_id,
                "mutations": self._transaction_mutations
        })

        self._transaction_mutations = []
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

