import logging
import warnings

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

try:
    from django.db.backends.schema import BaseDatabaseSchemaEditor
except ImportError:
    #Django < 1.6 doesn't have BaseDatabaseSchemaEditor
    class BaseDatabaseSchemaEditor(object):
        pass

from django.db.backends.creation import BaseDatabaseCreation
from django.db.models.sql.subqueries import InsertQuery, DeleteQuery
from django.db import models
from google.appengine.ext.db import metadata
from google.appengine.api import datastore
from google.appengine.api.datastore_types import Key, Text
from django.db.models.sql.constants import MULTI, SINGLE, GET_ITERATOR_CHUNK_SIZE
from django.db.models.sql.where import AND, OR
from django.utils.tree import Node

from django.core.cache import cache

from google.appengine.ext import testbed

from .commands import (
    SelectCommand, 
    InsertCommand, 
    FlushCommand
)

OPERATORS_MAP = {
    'exact': '=',
    'gt': '>',
    'gte': '>=',
    'lt': '<',
    'lte': '<=',

    # The following operators are supported with special code below.
    'isnull': None,
    'in': None,
    'startswith': None,
    'range': None,
    'year': None,
    'gt_and_lt': None #Special case combined filter
}

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
    field_values = {}

    primary_key = None
    for field in fields:
        value = field.get_db_prep_save(
            getattr(instance, field.attname) if raw else field.pre_save(instance, instance._state.adding),
            connection = connection
        )

        if (not field.null and not field.primary_key) and value is None:
            raise IntegrityError("You can't set %s (a non-nullable "
                                     "field) to None!" % field.name)

        if field.primary_key:
            primary_key = value
        else:
            value = connection.ops.value_for_db(value, field)
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

    entity = datastore.Entity(model._meta.db_table, **kwargs)
    entity.update(field_values)
    return entity

class Cursor(object):
    """ Dummy cursor class """
    def __init__(self, connection):
        self.connection = connection
        self.results = None
        self.queries = []
        self.start_cursor = None
        self.returned_ids = []
        self.queried_fields = []
        self.query_done = True
        self.all_filters = []
        self.last_query_model = None
        self.rowcount = -1

    def execute(self, sql, *params):
        if isinstance(sql, SelectCommand):
            combined_filters = []

            query = datastore.Query(
                sql.model._meta.db_table,
                projection=sql.projection
            )

            print(sql.where)

            for column, op, value in sql.where:
                final_op = OPERATORS_MAP[op]
                
                if final_op is None:
                    if op == "in":
                        combined_filters.append((column, op, value))
                        continue
                    elif op == "gt_and_lt":
                        combined_filters.append((column, op, value))
                        continue
                    assert(0)

                query["%s %s" % (column, final_op)] = value
            
            if combined_filters:
                queries = [ query ]
                for column, op, value in combined_filters:
                    new_queries = []
                    for query in queries:                        
                        if op == "in":
                            for val in value:
                                new_query = datastore.Query(sql.model._meta.db_table)
                                new_query.update(query)
                                new_query["%s =" % column] = val
                                new_queries.append(new_query)
                        elif op == "gt_and_lt":
                            for tmp_op in ("<", ">"):
                                new_query = datastore.Query(sql.model._meta.db_table)
                                new_query.update(query)
                                new_query["%s %s" % (column, tmp_op)] = value
                                new_queries.append(new_query)                        
                    queries = new_queries

                query = datastore.MultiQuery(queries, [])

            self.query = query
            self.results = None
            self.query_done = False
            self.queried_fields = sql.queried_fields
            self.last_query_model = sql.model
            self.aggregate_type = "count" if sql.is_count else None
            self._do_fetch()

        elif isinstance(sql, FlushCommand):
            sql.execute()
        elif isinstance(sql, InsertCommand):
            self.connection.queries.append(sql)

            self.returned_ids = datastore.Put(sql.entities)

            #Now cache them, temporarily to help avoid consistency errors
            for key, entity in zip(self.returned_ids, sql.entities):
                entity[sql.model._meta.pk.column] = key.id_or_name()
                cache_entity(sql.model, entity)

        else:
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


    def _run_query(self, limit=None, start=None, aggregate_type=None):
        if aggregate_type is None:
            return self.query.Run(limit=limit, start=start)
        elif self.aggregate_type == "count":
            return self.query.Count(limit=limit, start=start)
        else:
            raise RuntimeError("Unsupported query type")

    def _do_fetch(self):
        if not self.results:
            if isinstance(self.query, datastore.MultiQuery):
                self.results = self._run_query(aggregate_type=self.aggregate_type)
                self.query_done = True
            else:
                #Try and get the entity from the cache, this is to work around HRD issues
                #and boost performance!
                entity_from_cache = None
                if self.all_filters and self.last_query_model:
                    #Get all the exact filters
                    exact_filters = [ x for x in self.all_filters if x[1] == "=" ]
                    lookup = { x[0]:x[2] for x in exact_filters }

                    unique_combinations = get_uniques_from_model(self.last_query_model)
                    for fields in unique_combinations:
                        final_key = []
                        for field in fields:
                            if field in lookup:
                                final_key.append((field, lookup[field]))
                                continue
                            else:
                                break
                        else:
                            #We've found a unique combination!
                            unique_key = generate_unique_key(self.last_query_model, final_key)
                            entity_from_cache = get_entity_from_cache(unique_key)

                if entity_from_cache is None:
                    self.results = self._run_query(aggregate_type=self.aggregate_type)
                else:
                    self.results = [ entity_from_cache ]

            self.row_index = 0

    def next(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def fetchone(self, delete_flag=False):
        try:
            if isinstance(self.results, int):
                #Handle aggregate (e.g. count)
                return (self.results, )
            else:
                entity = self.results.next()
        except StopIteration:
            entity = None

        if entity is None:
            return None

        if delete_flag:
            uncache_entity(self.last_query_model, entity)      

        result = []
        for col in self.queried_fields:
            if col == "__key__":
                key = entity.key()
                self.returned_ids.append(key)
                result.append(key.id_or_name())
            else:
                result.append(entity.get(col))

        return result

    def fetchmany(self, size, delete_flag=False):
        if not self.results:
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

class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "djangae.db.backends.appengine.compiler"

    def quote_name(self, name):
        return name

    def sql_flush(self, style, tables, seqs, allow_cascade=False):
        return [ FlushCommand(table) for table in tables ]

    def value_for_db(self, value, field):
        from google.appengine.api.datastore_types import Blob, Text
        from google.appengine.api.datastore_errors import BadArgumentError, BadValueError

        if value is None:
            return None

        # Convert decimals to strings preserving order.
        if field.__class__.__name__ == 'DecimalField':
            value = decimal_to_string(
                value, field.max_digits, field.decimal_places)

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
