from django.db import IntegrityError, DatabaseError

class IntegrityError(IntegrityError, DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass

class CouldBeSupportedError(DatabaseError):
    pass
