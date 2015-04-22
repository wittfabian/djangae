"""This file exists for backwards compatability.
Please use the abstract or concrete models found in either:
`djangae.contrib.gauth.datastore` for applications using the datastore
backend or `djangae.contrib.gauth.sql` for applications using a relational
database backend
"""

import warnings
from exceptions import DeprecationWarning

from djangae.contrib.gauth.gauth_datastore.models import (
    GaeAbstractDatastoreUser, GaeDatastoreUser)


warnings.warn(
    'GaeAbstractDatastoreUser and GaeDatastoreUser have moved to '
    'djangae.contrib.gauth.datastore.models '
)
