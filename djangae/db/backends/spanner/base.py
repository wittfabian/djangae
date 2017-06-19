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

    _data_types = data_types = {
        'AutoField': FieldTypes.INT64,
        'BigAutoField': FieldTypes.INT64,
        'BinaryField': FieldTypes.BYTES + "(%(max_length)s)",
        'BooleanField': FieldTypes.BOOL,
        'CharField': FieldTypes.STRING + "(%(max_length)s)",
        'DateField': FieldTypes.TIMESTAMP,
        'DateTimeField': FieldTypes.TIMESTAMP,
        'DecimalField': FieldTypes.STRING + "(%(max_length)s)",
        'DurationField': FieldTypes.FLOAT64,
        'FileField': FieldTypes.STRING + "(%(max_length)s)",
        'FilePathField': FieldTypes.STRING + "(%(max_length)s)",
        'FloatField': FieldTypes.FLOAT64,
        'IntegerField': FieldTypes.INT64,
        'BigIntegerField': FieldTypes.INT64,
        'IPAddressField': FieldTypes.STRING + "(%(max_length)s)",
        'GenericIPAddressField': FieldTypes.STRING + "(%(max_length)s)",
        'NullBooleanField': FieldTypes.BOOL,
        'OneToOneField': FieldTypes.INT64,
        'PositiveIntegerField': FieldTypes.INT64,
        'PositiveSmallIntegerField': FieldTypes.INT64,
        'SlugField': FieldTypes.STRING + "(%(max_length)s)",
        'SmallIntegerField': FieldTypes.INT64,
        'TextField': FieldTypes.STRING + "(MAX)",
        'TimeField': FieldTypes.TIMESTAMP,
        'UUIDField': FieldTypes.STRING + "(%(max_length)s)",
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

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        if not self.ops:
            # If we're on a version of Django that doesn't do this automatically
            # do it! We can remove this at some point in the distant future!
            self.features = self.features_class(self)
            self.ops = self.ops_class(self)
            self.client = self.client_class(self)
            self.creation = self.creation_class(self)
            self.introspection = self.introspection_class(self)
            self.validation = self.validation_class(self)

    def _set_autocommit(self, autocommit):
        with self.wrap_database_errors:
            self.connection.autocommit(autocommit)

    def get_new_connection(self, conn_params):
        connection = Database.connect(**conn_params)
        return connection

    def quote_name(self):
        pass

    def init_connection_state(self):
        pass

    def get_connection_params(self):
        settings_dict = self.settings_dict
        return {
            'instance_id': settings_dict['INSTANCE'],
            'database_id': settings_dict['DATABASE'],
            'project_id': settings_dict['PROJECT'],
            'credentials_json': settings_dict.get('CREDENTIALS_JSON')
        }

    def create_cursor(self, name=None):
        cursor = self.connection.cursor()
        return cursor

