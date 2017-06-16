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
