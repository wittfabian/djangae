from django.db.backends.base.base import BaseDatabaseWrapper

from .impl import client as Database

from .client import DatabaseClient
from .creation import DatabaseCreation
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor
from .validation import DatabaseValidation


from .constants import FieldTypes


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'google'
    display_name = 'Cloud Spanner'

    _data_types = {
        'AutoField': FieldTypes.INT64,
        'BigAutoField': FieldTypes.INT64,
        'BinaryField': FieldTypes.BYTES,
        'BooleanField': FieldTypes.BOOL,
        'CharField': FieldTypes.STRING,
        'DateField': FieldTypes.TIMESTAMP,
        'DateTimeField': FieldTypes.TIMESTAMP,
        'DecimalField': FieldTypes.STRING,
        'DurationField': FieldTypes.FLOAT64,
        'FileField': FieldTypes.STRING,
        'FilePathField': FieldTypes.STRING,
        'FloatField': FieldTypes.FLOAT64,
        'IntegerField': FieldTypes.INT64,
        'BigIntegerField': FieldTypes.INT64,
        'IPAddressField': FieldTypes.STRING,
        'GenericIPAddressField': FieldTypes.STRING,
        'NullBooleanField': FieldTypes.BOOL,
        'OneToOneField': FieldTypes.INT64,
        'PositiveIntegerField': FieldTypes.INT64,
        'PositiveSmallIntegerField': FieldTypes.INT64,
        'SlugField': FieldTypes.STRING,
        'SmallIntegerField': FieldTypes.INT64,
        'TextField': FieldTypes.STRING,
        'TimeField': FieldTypes.TIMESTAMP,
        'UUIDField': FieldTypes.STRING,
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
    
