from django.db.models.sql import compiler
from djangae.db.backends.appengine.query import Query
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql.constants import MULTI, SINGLE, GET_ITERATOR_CHUNK_SIZE
from django.db import connections
from django.conf import settings

#Following two ImportError blocks are for < 1.6 compatibility
try:
    from django.db.models.sql.compiler import SQLDateCompiler as DateCompiler
except ImportError:
    class DateCompiler(object):
        pass

try:
    from django.db.models.sql.compiler import SQLDateTimeCompiler as DateTimeCompiler
except ImportError:
    class DateTimeCompiler(object):
        pass

from .base import django_instance_to_entity
from .commands import InsertCommand, SelectCommand

class SQLCompiler(compiler.SQLCompiler):
    query_class = Query

    def as_sql(self):

        queried_fields = []
        for x in self.query.select:
            if isinstance(x, tuple):
                #Django < 1.6 compatibility
                queried_fields.append(x[1])
            else:
                queried_fields.append(x.col[1])

        where = self.query.where.as_sql(
            qn=self.quote_name_unless_alias, 
            connection=self.connection
        )
    
        select = SelectCommand(
            self.connection,
            self.query.model, 
            queried_fields,
            where=self.query.where
        )

        print(where)
        return (select, [])

#    def execute_sql(self, result_type=MULTI):
#        try:
#            sql, params = self.as_sql()
#        except EmptyResultSet:
#            #This query couldn't match anything (e.g. thing__in=[])
#            sql = None

#        if not sql:
#            if result_type == MULTI:
#                return iter([])
#            else:
#                return None

#        cursor = self.connection.cursor()
#        cursor.execute_appengine_query(self.query.model, self.query)

#        # This at least satisfies the most basic unit tests.
#        if connections[self.using].use_debug_cursor or (connections[self.using].use_debug_cursor is None and settings.DEBUG):
#            self.connection.queries.append({'sql': repr(self.query)})

#        if not result_type:
#            return cursor
#        if result_type == SINGLE:
#            if self.ordering_aliases:
#                return cursor.fetchone()[:-len(self.ordering_aliases)]
#            return cursor.fetchone()
#
#        # The MULTI case.
#        if self.ordering_aliases:
#            result = order_modified_iter(cursor, len(self.ordering_aliases),
#                    self.connection.features.empty_fetchmany_value)
#        else:
#            result = iter((lambda: cursor.fetchmany(GET_ITERATOR_CHUNK_SIZE)),
#                    self.connection.features.empty_fetchmany_value)
#        if not self.connection.features.can_use_chunked_reads:
#            # If we are using non-chunked reads, we return the same data
#            # structure as normally, but ensure it is all read into memory
#            # before going any further.
#            return list(result)
#        return result

class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    def __init__(self, *args, **kwargs):
        self.return_id = None
        super(SQLInsertCompiler, self).__init__(*args, **kwargs)

    def as_sql(self):
        entities = [
            django_instance_to_entity(self.connection, self.query.model, self.query.fields, self.query.raw, x)
            for x in self.query.objs
        ]

        return [ (InsertCommand(self.query.model, entities), []) ]


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    def execute_sql(self, result_type=None):
        results = super(SQLDeleteCompiler, self).execute_sql()
        cursor = self.connection.cursor()
        cursor.execute_appengine_query(self.query.model, self.query)
        cursor.delete()        
        return


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass


class SQLDateCompiler(DateCompiler, SQLCompiler):
    pass


class SQLDateTimeCompiler(DateTimeCompiler, SQLCompiler):
    pass
