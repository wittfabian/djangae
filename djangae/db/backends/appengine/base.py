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

from django.db.models.sql.where import AND, OR
from django.utils.tree import Node

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

class Connection(object):
    """ Dummy connection class """
    def __init__(self, wrapper, params):
        self.creation = wrapper.creation
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
        self.queries = []
        self.start_cursor = None
        self.returned_ids = []
        self.queried_fields = []

    @property
    def query(self):
        return self.queries[0]
    
    @query.setter
    def query(self, value):
        if self.queries:
            self.queries[0] = value
        else:
            self.queries = [ value ]

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

    def _apply_filters(self, model, where, negated=False):
        if where.negated:
            negated = not negated
        
        if not negated and where.connector != AND:
            raise DatabaseError("Only AND filters are supported")
            
        for child in where.children:
            if isinstance(child, Node):
                self._apply_filters(model, child, negated)
                continue
                
            field, lookup_type, value = self._parse_child(model, child)
            self._apply_filter(model, field, lookup_type, negated, value)
        
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
                        new_query = self._apply_filter(model, field, 'exact', negated, v, query_to_update=new_query)
                        new_queries.append(new_query)
                                            
                self.queries = new_queries
                return
    
        if op is None:
            import pdb; pdb.set_trace()
                                                  
        assert(op is not None)
        
        query_to_update["%s %s" % (column, op)] = value
        return query_to_update
        
    def _parse_child(self, model, child):
        constraint, lookup_type, annotation, value = child
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
        
        #FIXME: Probably need to do some processing of the value here like
        #djangoappengine does    
        return field, lookup_type, value            
            
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
            self._apply_filters(model, query.where)

            try:
                self.queries[1]
                self.queries = [ datastore.MultiQuery(self.queries, []) ]
            except IndexError:
                pass


    def fetchmany(self, size):
        logging.error("NOT IMPLEMENTED: Called fetchmany")
        if self.results is None:
            if not self.queries:
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
        'TextField':                  'string',
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


