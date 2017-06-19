

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_unique = "CREATE UNIQUE INDEX %(name)s ON %(table)s(%(columns)s)"
    sql_delete_unique = "DROP INDEX %(name)s"

    sql_create_table = "CREATE TABLE %(table)s (%(definition)s) PRIMARY KEY(%%(_key_fields)s)"

    # Cloud Spanner doesn't support foreign keys (in the traditional sense)
    sql_create_fk = ""
    sql_delete_fk = ""

    sql_alter_column_type = "ALTER COLUMN %(column)s %(type)s"
    sql_alter_column_null = "ALTER COLUMN %(column)s %(type)s"
    sql_alter_column_null = "ALTER COLUMN %(column)s %(type)s NOT NULL"
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s"

    def skip_default(self, field):
        """
            Frustratingly, Cloud Spanner doesn't support DEFAULT at all
        """
        return True

    def create_model(self, model):
        """
            We have to store the model we are creating temporarily so that our hack in execute
            works.
        """
        try:
            self._creating_model = model
            self._unique_disabled = True
            return super(DatabaseSchemaEditor, self).create_model(model)
        finally:
            if hasattr(self, "_creating_model"):
                delattr(self, "_creating_model")

    def execute(self, sql, *args, **kwargs):
        """
            Horrible hack! Spanner requires PRIMARY KEY is positioned at the end of the
            CREATE TABLE statement. Unfortunately Django doesn't provide an easy way to hook
            into this. So we add an additional format param _key_fields into the create table SQL
            and substitute it in here

            Also unique and unique together constraints must be added in separate statements
            so we also hack that in here rather than overriding the whole of create_model and column_sql
        """

        if not sql:
            # Don't do anything if no SQL was provided which does happen
            # because we disable FKs (for example)
            return

        if getattr(self, "_creating_model", None):
            # Add primary key
            pk = self._creating_model._meta.pk
            sql = sql % {"_key_fields": pk.column}

            # add unique and unique together constraints
            model = self._creating_model
            delattr(self, "_unique_disabled")
            unique_queries = []

            for field in model._meta.local_fields:
                if field.unique:
                    unique_queries.append(self._create_unique_sql(model, [field.column]))

            for fields in model._meta.unique_together:
                columns = [model._meta.get_field(field).column for field in fields]
                unique_queries.append(self._create_unique_sql(model, columns))

            # Make a multi-statement query. The DB connector deals with splitting this
            # when running DDL queries
            if unique_queries:
                sql = sql + "; " + "; ".join(unique_queries)

        return super(DatabaseSchemaEditor, self).execute(sql, *args, **kwargs)

    def _create_unique_sql(self, model, columns):

        # This flag is necessary to prevent create_model adding unique sql
        # into the column definition
        if getattr(self, "_unique_disabled", False):
            return ""

        return super(DatabaseSchemaEditor, self)._create_unique_sql(model, columns)

    def column_sql(self, model, field, include_default=False):
        sql, params = super(DatabaseSchemaEditor, self).column_sql(model, field, include_default)

        # Cloud Spanner doesn't allow specifying a primary key alongside the column
        # it must instead by specified alongside indexes at the end of the create table statement
        sql = sql.replace(" PRIMARY KEY", "")

        # Remove unique keyword from column, it gets added later
        sql = sql.replace(" UNIQUE", "")

        return sql, params
