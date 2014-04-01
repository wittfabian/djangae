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

from .base import django_instance_to_entity, NotSupportedError
from .commands import InsertCommand, SelectCommand, UpdateCommand

from google.appengine.api import datastore

def validate_query_is_possible(query):
    """
        Need to check the following:

        - The query only has one inequality filter
        - The query does no joins
        - The query ordering is compatible with the filters
    """

    #Check for joins
    if query.count_active_tables() > 1:
        raise NotSupportedError("""
            The appengine database connector does not support JOINs. The requested join map follows\n
            %s
        """ % query.join_map)

class SQLCompiler(compiler.SQLCompiler):
    query_class = Query

    def as_sql(self):

        validate_query_is_possible(self.query)

        queried_fields = []
        for x in self.query.select:
            if isinstance(x, tuple):
                #Django < 1.6 compatibility
                queried_fields.append(x[1])
            else:
                queried_fields.append(x.col[1])

        #where = self.query.where.as_sql(
        #    qn=self.quote_name_unless_alias,
        #    connection=self.connection
        #)

        is_count = False
        if self.query.aggregates:
            if self.query.aggregates.keys() == [ None ]:
                if self.query.aggregates[None].col == "*":
                    is_count = True
                else:
                    raise NotSupportedError("Counting anything other than '*' is not supported")
            else:
                raise NotSupportedError("Unsupported aggregate query")

        opts = self.query.get_meta()
        if not self.query.default_ordering:
            ordering = self.query.order_by
        else:
            ordering = self.query.order_by or opts.ordering

        select = SelectCommand(
            self.connection,
            self.query.model,
            queried_fields,
            where=self.query.where,
            is_count=is_count,
            ordering=ordering
        )

        #print(where)
        return (select, [])

class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    def __init__(self, *args, **kwargs):
        self.return_id = None
        super(SQLInsertCompiler, self).__init__(*args, **kwargs)

    def as_sql(self):
        return [ (InsertCommand(self.connection, self.query.model, self.query.objs, self.query.fields, self.query.raw), []) ]

class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):

    def execute_sql(self, *args, **kwargs):
        result, params = SQLCompiler.as_sql(self)

        #Override the selected fields so we force a keys_only
        #query
        result.keys_only = True
        result.projection = None
        result.execute()

        datastore.Delete(result.results)


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):

    def __init__(self, *args, **kwargs):
        super(SQLUpdateCompiler, self).__init__(*args, **kwargs)

    def as_sql(self):
        return (UpdateCommand(self.connection, self.query.model, self.query.values, where=self.query.where), [])



class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass


class SQLDateCompiler(DateCompiler, SQLCompiler):
    pass


class SQLDateTimeCompiler(DateTimeCompiler, SQLCompiler):
    pass
