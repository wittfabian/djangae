from django.db.models.sql import compiler
from djangae.db.backends.appengine.query import Query

from django.db.models.sql.constants import MULTI

class SQLCompiler(compiler.SQLCompiler):
    query_class = Query
    
    def execute_sql(self, result_type=MULTI):
        pass
        
class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    pass

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
