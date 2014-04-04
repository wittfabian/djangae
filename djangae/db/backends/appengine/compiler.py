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

from .base import django_instance_to_entity, NotSupportedError, CouldBeSupportedError
from .commands import InsertCommand, SelectCommand, UpdateCommand, DeleteCommand

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

    if query.aggregates:
        if query.aggregates.keys() == [ None ]:
            if query.aggregates[None].col != "*":
                raise NotSupportedError("Counting anything other than '*' is not supported")
        else:
            raise NotSupportedError("Unsupported aggregate query")

    #This is a hack! Django < 1.7 sets an extra_select of a = 1 in has_results. In 1.7 this has
    #been moved to the compiler.
    if query.extra_select and query.extra_select != {'a': (u'1', [])}:
        raise CouldBeSupportedError("The appengine connector currently doesn't support extra_select, it can be implemented though")
                
class SQLCompiler(compiler.SQLCompiler):
    query_class = Query

    def as_sql(self):

        validate_query_is_possible(self.query)


        #where = self.query.where.as_sql(
        #    qn=self.quote_name_unless_alias,
        #    connection=self.connection
        #)

        select = SelectCommand(
            self.connection,
            self.query
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
    def as_sql(self):
        return (DeleteCommand(self.connection, self.query), [])

class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):

    def __init__(self, *args, **kwargs):
        super(SQLUpdateCompiler, self).__init__(*args, **kwargs)

    def as_sql(self):
        return (UpdateCommand(self.connection, self.query), [])



class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass


class SQLDateCompiler(DateCompiler, SQLCompiler):
    pass


class SQLDateTimeCompiler(DateTimeCompiler, SQLCompiler):
    pass
