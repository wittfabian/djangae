from django.db import IntegrityError

class DatabaseError(Exception):
    pass

class IntegrityError(IntegrityError, DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass

class CouldBeSupportedError(DatabaseError):
    pass
