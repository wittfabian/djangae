
from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    implied_column_null = True
    requires_literal_defaults = True

