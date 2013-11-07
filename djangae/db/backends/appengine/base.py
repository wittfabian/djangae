"""
Dummy database backend for Django.

Django uses this if the database ENGINE setting is empty (None or empty string).

Each of these API functions, except connection.close(), raises
ImproperlyConfigured.
"""

import logging
from itertools import islice

from django.core.exceptions import ImproperlyConfigured
from django.db.backends import (
    BaseDatabaseOperations,
    BaseDatabaseClient,
    BaseDatabaseIntrospection,
    BaseDatabaseWrapper,
    BaseDatabaseFeatures,
    BaseDatabaseValidation
)

from django.db.backends.schema import BaseDatabaseSchemaEditor
from django.db.backends.creation import BaseDatabaseCreation
from django.db.models.sql.subqueries import InsertQuery

from google.appengine.ext.db import metadata
from google.appengine.api import datastore

class DatabaseError(Exception):
    pass

class IntegrityError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass

class Connection(object):
    """ Dummy connection class """
    def __init__(self, wrapper, params):
        self.ops = wrapper.ops
        self.params = params

    def rollback(self):
        pass

    def commit(self):
        pass

    def close(self):
        pass

class Cursor(object):
    """ Dummy cursor class """
    def __init__(self, connection):
        self.connection = connection
        self.results = None
        self.query = None
        self.start_cursor = None
        self.returned_ids = []
        self.queried_fields = []

    def django_instance_to_entity(self, model, fields, raw, instance):
        field_values = {}

        for field in fields:

            value = field.get_db_prep_save(
                getattr(instance, field.attname) if raw else field.pre_save(instance, instance._state.adding),
                connection = self.connection
            )

            if (not field.null and not field.primary_key) and value is None:
                raise IntegrityError("You can't set %s (a non-nullable "
                                         "field) to None!" % field.name)

            #value = self.connection.ops.value_for_db(value, field)
            field_values[field.column] = value

        entity = datastore.Entity(model._meta.db_table)
        entity.update(field_values)
        return entity

    def execute(self, sql, *params):
        raise RuntimeError("Can't execute traditional SQL: '%s'", sql)

    def execute_appengine_query(self, model, query):
        if isinstance(query, InsertQuery):
            self.returned_ids = datastore.Put([ self.django_instance_to_entity(model, query.fields, query.raw, x) for x in query.objs ])

        else:
            #Store the fields we are querying on so we can process the results
            self.queried_fields = [ x.col[1] for x in query.select ]
            if self.queried_fields:
                projection = self.queried_fields
            else:
                projection = None
                self.queried_fields = [ x.column for x in model._meta.fields ]

            pk_field = model._meta.pk.name
            try:
                #Set the column name to __key__ and then we know the order it came
                #if the id was asked for
                self.queried_fields[self.queried_fields.index(pk_field)] = "__key__"
            except ValueError:
                pass

            self.query = datastore.Query(
                model._meta.db_table,
                projection=projection
            )

            #Apply filters



    def fetchmany(self, size):
        logging.error("NOT IMPLEMENTED: Called fetchmany")
        if self.results is None:
            if self.query is None:
                raise Database.Error()

            self.results = self.query.Run(limit=size, start=self.start_cursor)

        self.start_cursor = self.query.GetCursor()

        results = []
        for entity in self.results:
            result = []
            for col in self.queried_fields:
                if col == "__key__":
                    result.append(entity.key().id_or_name())
                else:
                    result.append(entity.get(col))

            results.append(tuple(result))
        return results

    @property
    def lastrowid(self):
        logging.error("NOT IMPLEMENTED: Last row id")
        return self.returned_ids[-1].id_or_name()

class Database(object):
    """ Fake DB API 2.0 for App engine """

    Error = DatabaseError
    DataError = DatabaseError
    DatabaseError = DatabaseError
    OperationalError = DatabaseError
    IntegrityError = IntegrityError
    InternalError = DatabaseError
    ProgrammingError = DatabaseError
    NotSupportedError = NotSupportedError
    InterfaceError = DatabaseError

class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "djangae.db.backends.appengine.compiler"

    def quote_name(self, name):
        return name

class DatabaseClient(BaseDatabaseClient):
    pass


class DatabaseCreation(BaseDatabaseCreation):
    def sql_create_model(self, model, *args, **kwargs):
        return [], {}

    def sql_for_pending_references(self, model, *args, **kwargs):
        return []

    def sql_indexes_for_model(self, model, *args, **kwargs):
        return []

class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        return metadata.get_kinds()

class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    def column_sql(self, model, field):
        return "", {}

    def create_model(self, model):
        """ Don't do anything when creating tables """
        pass

class DatabaseFeatures(BaseDatabaseFeatures):
    empty_fetchmany_value = []

class DatabaseWrapper(BaseDatabaseWrapper):
    operators = {
        'exact': '= %s',
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s'
    }

    Database = Database

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)

    def is_usable(self):
        return True

    def get_connection_params(self):
        return {}

    def get_new_connection(self, params):
        return Connection(self, params)

    def init_connection_state(self):
        pass

    def _set_autocommit(self, enabled):
        pass

    def create_cursor(self):
        return Cursor(self.connection)

    def schema_editor(self, *args, **kwargs):
        return DatabaseSchemaEditor(self, *args, **kwargs)


