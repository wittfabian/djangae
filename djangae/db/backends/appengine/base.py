import warnings
import datetime

from django.db.backends import (
    BaseDatabaseOperations,
    BaseDatabaseClient,
    BaseDatabaseIntrospection,
    BaseDatabaseWrapper,
    BaseDatabaseFeatures,
    BaseDatabaseValidation
)

try:
    from django.db.backends.schema import BaseDatabaseSchemaEditor
except ImportError:
    #Django < 1.6 doesn't have BaseDatabaseSchemaEditor
    class BaseDatabaseSchemaEditor(object):
        pass

from django.conf import settings
from django.utils import timezone
from django.db.backends.creation import BaseDatabaseCreation
from google.appengine.ext.db import metadata
from google.appengine.api import datastore
from google.appengine.api.datastore_types import Blob, Text
from django.db.models.sql.constants import GET_ITERATOR_CHUNK_SIZE
from django.db.backends.util import format_number
from django.core.cache import cache

from google.appengine.ext import testbed

from .commands import (
    SelectCommand,
    InsertCommand,
    FlushCommand,
    UpdateCommand,
    get_field_from_column
)

class DatabaseError(Exception):
    pass

class IntegrityError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass

DEFAULT_CACHE_TIMEOUT = 10

def cache_entity(model, entity):
    unique_combinations = get_uniques_from_model(model)

    unique_keys = []
    for fields in unique_combinations:
        key_parts = []
        for x in fields:
            if x == model._meta.pk.column and x not in entity:
                value = entity.key().id_or_name()
            else:
                value = entity[x]

            key_parts.append((x, value))

        unique_keys.append(generate_unique_key(model, key_parts))

    for key in unique_keys:
        #logging.error("Caching entity with key %s", key)
        cache.set(key, entity, DEFAULT_CACHE_TIMEOUT)

def uncache_entity(model, entity):
    unique_combinations = get_uniques_from_model(model)

    unique_keys = []
    for fields in unique_combinations:
        key_parts = []
        for x in fields:
            if x == model._meta.pk.column and x not in entity:
                value = entity.key().id_or_name()
            else:
                value = entity[x]
            key_parts.append((x, value))

        key = generate_unique_key(model, key_parts)
        cache.delete(key)

def get_uniques_from_model(model):
    uniques = [ [ model._meta.get_field(y).column for y in x ] for x in model._meta.unique_together ]
    uniques.extend([[x.column] for x in model._meta.fields if x.unique])
    return uniques

def generate_unique_key(model, fields_and_values):
    fields_and_values = sorted(fields_and_values, key=lambda x: x[0]) #Sort by field name

    key = '%s.%s|' % (model._meta.app_label, model._meta.db_table)
    key += '|'.join(['%s:%s' % (field, value) for field, value in fields_and_values])
    return key

def get_entity_from_cache(key):
    entity = cache.get(key)
#    if entity:
#        logging.error("Got entity from cache with key %s", key)
    return entity

class Connection(object):
    """ Dummy connection class """
    def __init__(self, wrapper, params):
        self.creation = wrapper.creation
        self.ops = wrapper.ops
        self.params = params
        self.queries = []

    def rollback(self):
        pass

    def commit(self):
        pass

    def close(self):
        pass

def django_instance_to_entity(connection, model, fields, raw, instance):
    uses_inheritance = False
    inheritance_root = model
    db_table = model._meta.db_table

    def value_from_instance(_instance, _field):
        value = getattr(_instance, _field.attname) if raw else _field.pre_save(_instance, _instance._state.adding)

        value = _field.get_db_prep_save(
            value,
            connection = connection
        )

        if (not _field.null and not _field.primary_key) and value is None:
            raise IntegrityError("You can't set %s (a non-nullable "
                                     "field) to None!" % _field.name)

        is_primary_key = False
        if _field.primary_key and _field.model == inheritance_root:
            is_primary_key = True

        value = connection.ops.value_for_db(value, _field)

        return value, is_primary_key

    if [ x for x in model._meta.get_parent_list() if not x._meta.abstract]:
        #We can simulate multi-table inheritance by using the same approach as
        #datastore "polymodels". Here we store the classes that form the heirarchy
        #and extend the fields to include those from parent models
        classes = [ model._meta.db_table ]
        for parent in model._meta.get_parent_list():
            if not parent._meta.parents:
                #If this is the top parent, override the db_table
                db_table = parent._meta.db_table
                inheritance_root = parent

            classes.append(parent._meta.db_table)
            for field in parent._meta.fields:
                fields.append(field)

        uses_inheritance = True


    #FIXME: This will only work for two levels of inheritance
    for obj in model._meta.get_all_related_objects():
        if model in [ x for x in obj.model._meta.parents if not x._meta.abstract]:
            try:
                related_obj = getattr(instance, obj.var_name)
            except obj.model.DoesNotExist:
                #We don't have a child attached to this field
                #so ignore
                continue

            for field in related_obj._meta.fields:
                fields.append(field)

    field_values = {}
    primary_key = None

    # primary.key = self.model._meta.pk
    for field in fields:
        value, is_primary_key = value_from_instance(instance, field)
        if is_primary_key:
            primary_key = value
        else:
            field_values[field.column] = value

    kwargs = {}
    if primary_key:
        if isinstance(primary_key, int):
            kwargs["id"] = primary_key
        elif isinstance(primary_key, basestring):
            if len(primary_key) >= 500:
                warnings.warn("Truncating primary key"
                    " that is over 500 characters. THIS IS AN ERROR IN YOUR PROGRAM.",
                    RuntimeWarning
                )
                primary_key = primary_key[:500]

            kwargs["name"] = primary_key
        else:
            raise ValueError("Invalid primary key value")

    entity = datastore.Entity(db_table, **kwargs)
    entity.update(field_values)

    if uses_inheritance:
        entity["class"] = classes

    #print inheritance_root.__name__ if inheritance_root else "None", model.__name__, entity
    return entity

class Cursor(object):
    """ Dummy cursor class """
    def __init__(self, connection):
        self.connection = connection
        self.start_cursor = None
        self.returned_ids = []
        self.rowcount = -1
        self.last_select_command = None
        self.last_delete_command = None

    def execute(self, sql, *params):
        if isinstance(sql, SelectCommand):
            #Also catches subclasses of SelectCommand (e.g Update)
            self.last_select_command = sql
            self.rowcount = self.last_select_command.execute() or -1
        elif isinstance(sql, FlushCommand):
            sql.execute()
        elif isinstance(sql, UpdateCommand):
            self.rowcount = sql.execute()
        elif isinstance(sql, InsertCommand):
            self.connection.queries.append(sql)

            self.returned_ids = datastore.Put(sql.entities)

            #Now cache them, temporarily to help avoid consistency errors
            for key, entity in zip(self.returned_ids, sql.entities):
                pk_column = sql.model._meta.pk.column

                #If there are parent models, search the parents for the
                #first primary key which isn't a relation field
                for parent in sql.model._meta.parents.keys():
                    if not parent._meta.pk.rel:
                        pk_column = parent._meta.pk.column

                entity[pk_column] = key.id_or_name()
                cache_entity(sql.model, entity)
        else:
            import pdb;pdb.set_trace()
            raise RuntimeError("Can't execute traditional SQL: '%s'", sql)

    def fix_fk_null(self, query, constraint):
        alias = constraint.alias
        table_name = query.alias_map[alias][TABLE_NAME]
        lhs_join_col, rhs_join_col = join_cols(query.alias_map[alias])
        if table_name != constraint.field.rel.to._meta.db_table or \
                rhs_join_col != constraint.field.rel.to._meta.pk.column or \
                lhs_join_col != constraint.field.column:
            return
        next_alias = query.alias_map[alias][LHS_ALIAS]
        if not next_alias:
            return
        self.unref_alias(query, alias)
        alias = next_alias
        constraint.col = constraint.field.column
        constraint.alias = alias

    def next(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def fetchone(self, delete_flag=False):
        try:
            if isinstance(self.last_select_command.results, int):
                #Handle aggregate (e.g. count)
                return (self.last_select_command.results, )
            else:
                entity = self.last_select_command.results.next()
        except StopIteration:
            entity = None

        if entity is None:
            return None

        if delete_flag:
            uncache_entity(self.last_select_command.model, entity)

        result = []
        for col in self.last_select_command.queried_fields:
            if col == "__key__":
                key = entity.key()
                self.returned_ids.append(key)
                result.append(key.id_or_name())
            else:
                value = entity.get(col)
                field = get_field_from_column(self.last_select_command.model, col)

                type = field.get_internal_type()
                if type == "DateTimeField":
                    value = self.connection.ops.value_from_db_datetime(value)
                elif type == "DateField":
                    value = self.connection.ops.value_from_db_date(value)
                elif type == "TimeField":
                    value = self.connection.ops.value_from_db_time(value)
                elif type == "DecimalField":
                    value = self.connection.ops.value_from_db_decimal(value)

                result.append(value)

        return result

    def fetchmany(self, size, delete_flag=False):
        if not self.last_select_command.results:
            return []

        result = []
        i = 0
        while i < size:
            entity = self.fetchone(delete_flag)
            if entity is None:
                break

            result.append(entity)
            i += 1

        return result

    def delete(self):
        #Passing the delete_flag will uncache the entities
        self.fetchmany(GET_ITERATOR_CHUNK_SIZE, delete_flag=True)
        datastore.Delete(self.returned_ids)

    @property
    def lastrowid(self):
        return self.returned_ids[-1].id_or_name()

    def __iter__(self):
        return self

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

def make_timezone_naive(value):
    if value is None:
        return None

    if timezone.is_aware(value):
        if settings.USE_TZ:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            raise ValueError("Djangae backend does not support timezone-aware datetimes when USE_TZ is False.")
    return value

def decimal_to_string(value, max_digits=16, decimal_places=0):
    """
    Converts decimal to a unicode string for storage / lookup by nonrel
    databases that don't support decimals natively.

    This is an extension to `django.db.backends.util.format_number`
    that preserves order -- if one decimal is less than another, their
    string representations should compare the same (as strings).

    TODO: Can't this be done using string.format()?
          Not in Python 2.5, str.format is backported to 2.6 only.
    """

    # Handle sign separately.
    if value.is_signed():
        sign = u'-'
        value = abs(value)
    else:
        sign = u''

    # Let Django quantize and cast to a string.
    value = format_number(value, max_digits, decimal_places)

    # Pad with zeroes to a constant width.
    n = value.find('.')
    if n < 0:
        n = len(value)
    if n < max_digits - decimal_places:
        value = u'0' * (max_digits - decimal_places - n) + value
    return sign + value

class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "djangae.db.backends.appengine.compiler"

    def quote_name(self, name):
        return name

    def sql_flush(self, style, tables, seqs, allow_cascade=False):
        return [ FlushCommand(table) for table in tables ]

    def value_for_db(self, value, field):
        if value is None:
            return None

        db_type = self.connection.creation.db_type(field)

        if db_type == 'string' or db_type == 'text':
            if isinstance(value, str):
                value = value.decode('utf-8')
            if db_type == 'text':
                value = Text(value)
        elif db_type == 'bytes':
            # Store BlobField, DictField and EmbeddedModelField values as Blobs.
            value = Blob(value)

        return value

    def last_insert_id(self, cursor, db_table, column):
        return cursor.lastrowid

    def fetch_returned_insert_id(self, cursor):
        return cursor.lastrowid

    def value_to_db_datetime(self, value):
        value = make_timezone_naive(value)
        return value

    def value_to_db_date(self, value):
        return value

    def value_to_db_time(self, value):
        value = make_timezone_naive(value)
        return value

    def value_to_db_decimal(self, value, max_digits, decimal_places):
        return decimal_to_string(value, max_digits, decimal_places)

    ##Unlike value_to_db, these are not overridden or standard Django, it's just nice to have symmetry
    def value_from_db_datetime(self, value):
        if isinstance(value, long):
            #App Engine Query's don't return datetime fields (unlike Get) I HAVE NO IDEA WHY, APP ENGINE SUCKS MONKEY BALLS
            value = datetime.datetime.fromtimestamp(float(value) / 1000000.0)

        if value is not None and settings.USE_TZ and timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value

    def value_from_db_date(self, value):
        if isinstance(value, long):
            #App Engine Query's don't return datetime fields (unlike Get) I HAVE NO IDEA WHY, APP ENGINE SUCKS MONKEY BALLS
            value = datetime.datetime.fromtimestamp(float(value) / 1000000.0).date()

        if value is not None and settings.USE_TZ and timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value.date()

    def value_from_db_time(self, value):
        if isinstance(value, long):
            #App Engine Query's don't return datetime fields (unlike Get) I HAVE NO IDEA WHY, APP ENGINE SUCKS MONKEY BALLS
            value = datetime.datetime.fromtimestamp(float(value) / 1000000.0).time()

        if value is not None and settings.USE_TZ and timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value.time()

    def value_from_db_decimal(self, value):
        return value

class DatabaseClient(BaseDatabaseClient):
    pass


class DatabaseCreation(BaseDatabaseCreation):
    data_types = {
        'AutoField':                  'key',
        'RelatedAutoField':           'key',
        'ForeignKey':                 'key',
        'OneToOneField':              'key',
        'ManyToManyField':            'key',
        'BigIntegerField':            'long',
        'BooleanField':               'bool',
        'CharField':                  'string',
        'CommaSeparatedIntegerField': 'string',
        'DateField':                  'date',
        'DateTimeField':              'datetime',
        'DecimalField':               'decimal',
        'EmailField':                 'string',
        'FileField':                  'string',
        'FilePathField':              'string',
        'FloatField':                 'float',
        'ImageField':                 'string',
        'IntegerField':               'integer',
        'IPAddressField':             'string',
        'NullBooleanField':           'bool',
        'PositiveIntegerField':       'integer',
        'PositiveSmallIntegerField':  'integer',
        'SlugField':                  'string',
        'SmallIntegerField':          'integer',
        'TimeField':                  'time',
        'URLField':                   'string',
        'AbstractIterableField':      'list',
        'ListField':                  'list',
        'RawField':                   'raw',
        'BlobField':                  'bytes',
        'TextField':                  'text',
        'XMLField':                   'text',
        'SetField':                   'list',
        'DictField':                  'bytes',
        'EmbeddedModelField':         'bytes'
    }

    def db_type(self, field):
        return self.data_types[field.__class__.__name__]

    def __init__(self, *args, **kwargs):
        self.testbed = None
        super(DatabaseCreation, self).__init__(*args, **kwargs)

    def sql_create_model(self, model, *args, **kwargs):
        return [], {}

    def sql_for_pending_references(self, model, *args, **kwargs):
        return []

    def sql_indexes_for_model(self, model, *args, **kwargs):
        return []

    def _create_test_db(self, verbosity, autoclobber):

        # Testbed exists in memory
        test_database_name = ':memory:'

        # Init test stubs
        self.testbed = testbed.Testbed()
        self.testbed.activate()

        self.testbed.init_app_identity_stub()
        self.testbed.init_blobstore_stub()
        self.testbed.init_capability_stub()
        self.testbed.init_channel_stub()

        self.testbed.init_datastore_v3_stub()
        self.testbed.init_files_stub()
        # FIXME! dependencies PIL
        # self.testbed.init_images_stub()
        self.testbed.init_logservice_stub()
        self.testbed.init_mail_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_taskqueue_stub()
        self.testbed.init_urlfetch_stub()
        self.testbed.init_user_stub()
        self.testbed.init_xmpp_stub()
        # self.testbed.init_search_stub()

        # Init all the stubs!
        # self.testbed.init_all_stubs()

        return test_database_name


    def _destroy_test_db(self, name, verbosity):
        if self.testbed:
            self.testbed.deactivate()


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
    supports_transactions = False #FIXME: Make this True!
    can_return_id_from_insert = True
    supports_select_related = False

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
        conn = Connection(self, params)
        return conn

    def init_connection_state(self):
        pass

    def _set_autocommit(self, enabled):
        pass

    def create_cursor(self):
        if not self.connection:
            self.connection = self.get_new_connection(self.settings_dict)

        return Cursor(self.connection)

    def schema_editor(self, *args, **kwargs):
        return DatabaseSchemaEditor(self, *args, **kwargs)

    def _cursor(self):
        #for < Django 1.6 compatiblity
        return self.create_cursor()
