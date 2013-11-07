"""
Dummy database backend for Django.

Django uses this if the database ENGINE setting is empty (None or empty string).

Each of these API functions, except connection.close(), raises
ImproperlyConfigured.
"""

import logging

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
    def __init__(self, params):
        self.params = params

    def rollback(self):
        pass

    def commit(self):
        pass
        
    def close(self):
        pass

class Cursor(object):
    """ Dummy cursor class """
    def execute(self, sql, *params):
        import pdb; pdb.set_trace();
        logging.error("Running Gql Query: '%s'", sql)
        self.results = datastore.Query(sql, *params)

    def execute_appengine_query(self, model, params):
        pass

    def fetchmany(self, size):
        logging.error("NOT IMPLEMENTED: Called fetchmany")
        results = self.results[:size]
        self.results = self.results[size:]
        return results
        
    @property
    def lastrowid(self):
        logging.error("NOT IMPLEMENTED: Last row id")
        pass

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
    pass


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        return metadata.get_kinds()
        
class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    def column_sql(self, model, field):
        return "", {}

    def create_model(self, model):
        """ Don't do anything when creating tables """
        pass

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

        self.features = BaseDatabaseFeatures(self)
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
        return Connection(params)
        
    def init_connection_state(self):
        pass
        
    def _set_autocommit(self, enabled):
        pass
        
    def create_cursor(self):
        return Cursor()
        
    def schema_editor(self, *args, **kwargs):
        return DatabaseSchemaEditor(self, *args, **kwargs)
        

