
from django.db.models.sql import compiler
from django.utils.encoding import force_text, force_bytes


class SQLCompiler(compiler.SQLCompiler):
    pass


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    def as_sql(self):
        has_fields = bool(self.query.fields)

        queries = super(SQLInsertCompiler, self).as_sql()

        if not has_fields:
            return queries

        # For string/bytes types we MUST ensure that the values are the correct type
        # (e.g. unicode for string, str for bytes, or str/bytes on Py3). This is because
        # Spanner doesn't implicitly cast from one to the other and the connector
        # has to indicate which type each field is

        field_types = [x.db_type(self.connection) for x in self.query.fields]

        # Go through the queries, enforce the correct types
        for sql, params in queries:
            for i, field_type in enumerate(field_types):
                if field_type.startswith("STRING("):
                    params[i] = force_text(params[i])
                elif field_type.startswith("BYTES("):
                    params[i] = force_bytes(params[i])

        return queries


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
