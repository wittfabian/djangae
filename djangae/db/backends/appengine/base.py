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

from django.db.models.sql.where import AND, OR
from django.utils.tree import Node

from django.core.cache import cache

from google.appengine.ext import testbed


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

class FlushCommand(object):
    """
        sql_flush returns the SQL statements to flush the database,
        which are then executed by cursor.execute()

        We instead return a list of FlushCommands which are called by
        our cursor.execute
    """
    def __init__(self, table):
        self.table = table

    def execute(self):
        table = self.table

        all_the_things = list(datastore.Query(table, keys_only=True).Run())
        while all_the_things:
            datastore.Delete(all_the_things)
            all_the_things = list(datastore.Query(table, keys_only=True).Run())

        cache.clear()

class InsertCommand(object):
    def __init__(self, model, entities):
        if model._meta.get_parent_list() and not model._meta.abstract:
            raise RuntimeError("Multi-table inheritance is not supported")

        self.entities = entities
        self.model = model

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

    @property
    def query(self):
        return self.queries[0]

    @query.setter
    def query(self, value):
        if self.queries:
            self.queries[0] = value
        else:
            self.queries = [ value ]

    def execute(self, sql, *params):
        if isinstance(sql, FlushCommand):
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

    def _update_projection_state(self, field, lookup_type):
        db_type = field.db_type(self.connection)

        disable_projection = False
        projected_fields = self.query.GetQueryOptions().projection

        if not projected_fields or field.column not in projected_fields:
            return

        if db_type in ("text", "bytes"):
            disable_projection = True

        if lookup_type in ('exact', 'in'):
            disable_projection = True

        if disable_projection:
            new_queries = []
            for query in self.queries:
                new_query = datastore.Query(query._Query__kind) #Nasty
                new_query.update(query)
                new_queries.append(new_query)

            self.queries = new_queries

    def _apply_filters(self, model, where, all_filters, negated=False):
        if where.negated:
            negated = not negated

        if not negated and where.connector != AND:
            raise DatabaseError("Only AND filters are supported")

        for child in where.children:
            if isinstance(child, Node):
                self._apply_filters(model, child, all_filters, negated=negated)
                continue

            field, lookup_type, value = self._parse_child(model, child)
            applied_filter = self._apply_filter(model, field, lookup_type, negated, value)
            if applied_filter is not None:
                #IN queries return None here, all_filters is empty on an IN query
                all_filters.append(applied_filter)

        if where.negated:
            negated = not negated

    def _apply_filter(self, model, field, lookup_type, negated, value, query_to_update=None):
        query_to_update = query_to_update or self.query

        if lookup_type not in OPERATORS_MAP:
            raise DatabaseError("Lookup type %r isn't supported." % lookup_type)

        column = field.column
        if field.primary_key:
            column = "__key__"

        #Disable projection queries if neccessary
        self._update_projection_state(field, lookup_type)

        op = OPERATORS_MAP.get(lookup_type)

        if op is None:
            if lookup_type == "in":
                new_queries = []
                for query in self.queries:
                    for v in value:
                        new_query = datastore.Query(model._meta.db_table)
                        new_query.update(query)
                        self._apply_filter(model, field, 'exact', negated, v, query_to_update=new_query)
                        new_queries.append(new_query)

                self.queries = new_queries
                return
            elif lookup_type == "isnull":
                op = "="
                value = None

        if op is None:
            import pdb; pdb.set_trace()

        assert(op is not None)

        query_to_update["%s %s" % (column, op)] = value
        return (column, op, value)

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

    def _parse_child(self, model, child):
        constraint, lookup_type, annotation, value = child

        if constraint.field is not None and lookup_type == 'isnull' and \
            isinstance(constraint.field, models.ForeignKey):
            self.fix_fk_null(self.query, constraint)

        packed, value = constraint.process(lookup_type, value, self.connection)
        alias, column, db_type = packed
        field = constraint.field

        #FIXME: Add support for simple inner joins
        opts = model._meta
        if alias and alias != opts.db_table:
            raise DatabaseError("This database doesn't support JOINs "
                                "and multi-table inheritance.")

        # For parent.child_set queries the field held by the constraint
        # is the parent's primary key, while the field the filter
        # should consider is the child's foreign key field.
        if column != field.column:
            assert field.primary_key
            field = opts.get_field(column[:-3]) #Remove _id
            assert field.rel is not None

        def normalize_value(_value, _lookup_type, _annotation):
            # Undo Field.get_db_prep_lookup putting most values in a list
            # (a subclass may override this, so check if it's a list) and
            # losing the (True / False) argument to the "isnull" lookup.
            if _lookup_type not in ('in', 'range', 'year') and \
               isinstance(value, (tuple, list)):
                if len(_value) > 1:
                    raise DatabaseError("Filter lookup type was %s; expected the "
                                        "filter argument not to be a list. Only "
                                        "'in'-filters can be used with lists." %
                                        lookup_type)
                elif lookup_type == 'isnull':
                    _value = _annotation
                else:
                    _value = _value[0]

            # Remove percents added by Field.get_db_prep_lookup (useful
            # if one were to use the value in a LIKE expression).
            if _lookup_type in ('startswith', 'istartswith'):
                _value = _value[:-1]
            elif _lookup_type in ('endswith', 'iendswith'):
                _value = _value[1:]
            elif _lookup_type in ('contains', 'icontains'):
                _value = _value[1:-1]

            if field.primary_key:
                if isinstance(_value, (list, tuple)):
                    _value = [ Key.from_path(field.model._meta.db_table, x) for x in _value]
                else:
                    _value = Key.from_path(field.model._meta.db_table, _value)

            return _value

        #FIXME: Probably need to do some processing of the value here like
        #djangoappengine does
        return field, lookup_type, normalize_value(value, lookup_type, annotation)

    def execute_appengine_query(self, model, query):
        if model._meta.get_parent_list() and not model._meta.abstract:
            raise RuntimeError("Multi-table inheritance is not supported")

        #Store the fields we are querying on so we can process the results
        self.queried_fields = []
        for x in query.select:
            if isinstance(x, tuple):
                #Django < 1.6 compatibility
                self.queried_fields.append(x[1])
            else:
                self.queried_fields.append(x.col[1])

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

        self.all_filters = []
        #Apply filters
        self._apply_filters(model, query.where, self.all_filters)

        try:
            self.queries[1]
            self.queries = [ datastore.MultiQuery(self.queries, []) ]
        except IndexError:
            pass
        self.last_query_model = model

        self.query_done = False


    def fetchone(self):
        try:
            return self.fetchmany(1)[0]
        except IndexError:
            return None


    def fetchmany(self, size, delete_flag=False):
        if self.query_done:
            return []

        if self.results is None:
            if not self.queries:
                raise Database.Error()

            if isinstance(self.query, datastore.MultiQuery):
                self.results = self.query.Run()
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
                    self.results = self.query.Run(limit=size, start=self.start_cursor)
                    self.start_cursor = self.query.GetCursor()
                    self.query_done = not self.results
                else:
                    self.results = [ entity_from_cache ]
                    self.query_done = True
                    self.start_cursor = None

        # If exit here don't have to parse the results, for deletion
        if delete_flag:
            return

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

    def delete(self):
        [ uncache_entity(self.last_query_model, e) for e in self.results ]
        datastore.Delete(self.results)

    @property
    def lastrowid(self):
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

