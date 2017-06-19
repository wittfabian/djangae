import datetime
from django.db.backends.base.operations import BaseDatabaseOperations
from django.utils import timezone


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = 'djangae.db.backends.spanner.compiler'

    def max_name_length(self):
        return 128

    def quote_name(self, name):
        if name.startswith("`") and name.endswith("`"):
            return name  # Quoting once is enough.
        return "`%s`" % name

    def sql_flush(self, style, tables, sequences, allow_cascade=False):
        """
            Cloud Spanner doesn't support TRUNCATE and due to limitations, you can't
            just delete all the rows from a table. So the only option is to work out the
            DDL needed to recreate the tables and indexes, then drop them all, then create
            them all.
        """

        def list_indexes(table):
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW INDEX FROM %s" % table);
                return [x[0] for x in cursor.fetchall()]

        def query_ddl(object_list):
            "Given a list of tables or indexes, return the DDL statements in a dictionary"

            result = {}
            for name in object_list:
                with self.connection.cursor() as cursor:
                    cursor.execute("SHOW DDL %s" % name);
                    ddl = cursor.fetchone()
                    result[name] = ddl
            return result

        if tables:
            objects = []
            sql = []

            for table in tables:
                objects.append(table)

                indexes = list_indexes(table)
                for index in indexes:
                    objects.append(index)
                    sql.append("DROP INDEX %s" % index)
                sql.append("DROP TABLE %s" % table)

            # Get all DDL creation statements for tables and indexes
            ddl_statements = query_ddl(objects)

            # Add the SQL for recreating the tables
            for table in tables:
                sql.append(ddl_statements[table])

            # Add the SQL for creating the indexes
            for obj, ddl in ddl_statements.items():
                if obj not in tables:
                    sql.append(ddl)

        else:
            return []


    def adapt_date_value(self, value):
        """
        Transforms a date value to an object compatible with what is expected
        by the backend driver for date columns.
        """
        if value is None:
            return None
        assert(isinstance(value, datetime.date))
        return value

    def adapt_datetimefield_value(self, value):
        """
        Transforms a datetime value to an object compatible with what is expected
        by the backend driver for datetime columns.
        """
        if value is None:
            return None

        assert(isinstance(value, datetime.datetime))
        return value

    def adapt_timefield_value(self, value):
        """
        Transforms a time value to an object compatible with what is expected
        by the backend driver for time columns.
        """
        if value is None:
            return None
        if timezone.is_aware(value):
            raise ValueError("Django does not support timezone-aware times.")
        assert(isinstance(value, datetime.time))
        return value

    value_to_db_date = adapt_date_value
    value_to_db_datetime = adapt_datetimefield_value
    value_to_db_time = adapt_timefield_value # Django 1.8
