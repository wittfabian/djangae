from django.db.models.sql import compiler
from djangae.db.backends.appengine.query import Query

from django.db.models.sql.constants import MULTI, SINGLE, GET_ITERATOR_CHUNK_SIZE

class SQLCompiler(compiler.SQLCompiler):
    query_class = Query

    def execute_sql(self, result_type=MULTI):
        sql, params = self.as_sql()
        if not sql:
            if result_type == MULTI:
                return iter([])
            else:
                return None

        cursor = self.connection.cursor()
        cursor.execute_appengine_query(self.query.model, self.query)

        if not result_type:
            return cursor
        if result_type == SINGLE:
            if self.ordering_aliases:
                return cursor.fetchone()[:-len(self.ordering_aliases)]
            return cursor.fetchone()

        # The MULTI case.
        if self.ordering_aliases:
            result = order_modified_iter(cursor, len(self.ordering_aliases),
                    self.connection.features.empty_fetchmany_value)
        else:
            result = iter((lambda: cursor.fetchmany(GET_ITERATOR_CHUNK_SIZE)),
                    self.connection.features.empty_fetchmany_value)
        if not self.connection.features.can_use_chunked_reads:
            # If we are using non-chunked reads, we return the same data
            # structure as normally, but ensure it is all read into memory
            # before going any further.
            return list(result)
        return result

class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    def execute_sql(self, return_id=False):
        assert not (return_id and len(self.query.objs) != 1)
        self.return_id = return_id
        cursor = self.connection.cursor()
        cursor.execute_appengine_query(self.query.model, self.query)
        if not (return_id and cursor):
            return
        if self.connection.features.can_return_id_from_insert:
            return self.connection.ops.fetch_returned_insert_id(cursor)
        return self.connection.ops.last_insert_id(cursor,
                self.query.get_meta().db_table, self.query.get_meta().pk.column)

class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass


class SQLDateCompiler(compiler.SQLDateCompiler, SQLCompiler):
    pass


class SQLDateTimeCompiler(compiler.SQLDateTimeCompiler, SQLCompiler):
    pass
