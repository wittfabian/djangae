

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_table = "CREATE TABLE %(table)s (%(definition)s) PRIMARY KEY(%%(_key_fields)s)"

    def create_model(self, model):
        """
            We have to store the model we are creating temporarily so that our hack in execute
            works.
        """
        try:
            self._creating_model = model
            return super(DatabaseSchemaEditor, self).create_model(model)
        finally:
            delattr(self, "_creating_model")

    def execute(self, sql, *args, **kwargs):
        """
            Horrible hack! Spanner requires PRIMARY KEY is positioned at the end of the
            CREATE TABLE statement. Unfortunately Django doesn't provide an easy way to hook
            into this. So we add an additional format param _key_fields into the create table SQL
            and substitute it in here
        """

        if getattr(self, "_creating_model", None):
            pk = self._creating_model._meta.pk
            sql = sql % {"_key_fields": pk.column}

        return super(DatabaseSchemaEditor, self).execute(sql, *args, **kwargs)

    def column_sql(self, model, field, include_default=False):
        sql, params = super(DatabaseSchemaEditor, self).column_sql(model, field, include_default)

        # Cloud Spanner doesn't allow specifying a primary key alongside the column
        # it must instead by specified alongside indexes at the end of the create table statement
        sql = sql.replace(" PRIMARY KEY", "")

        return sql, params
