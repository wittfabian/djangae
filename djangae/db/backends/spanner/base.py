from django.db.backends.base.base import BaseDatabaseWrapper

from .impl import client as Database

from .client import DatabaseClient
from .creation import DatabaseCreation
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor
from .validation import DatabaseValidation


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'google'
    display_name = 'Cloud Spanner'

    _data_types = {

    }

    operators = {

    }

    Database = Database
    SchemaEditorClass = DatabaseSchemaEditor
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations
    validation_class = DatabaseValidation

    def get_new_connection(self, conn_params):
        return Database.connect(**conn_params)

    def create_cursor(self):
        cursor = self.connection.cursor()
        return cursor
    
