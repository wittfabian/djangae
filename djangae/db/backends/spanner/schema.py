

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    def column_sql(self, model, field, include_default=False):
        sql, params = super(DatabaseSchemaEditor, self).column_sql(model, field, include_default)

        # Cloud Spanner doesn't allow specifying a primary key alongside the column
        # it must instead by specified alongside indexes at the end of the create table statement
        sql = sql.replace(" PRIMARY KEY", "")

        return sql, params
