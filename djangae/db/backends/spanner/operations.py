
from django.db.backends.base.operations import BaseDatabaseOperations


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = 'djangae.db.backends.spanner.compiler'

    def max_name_length(self):
        return 128
