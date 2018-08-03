
from google.appengine.api.datastore import MAX_ALLOWABLE_QUERIES
from google.appengine.api.datastore import Delete as _Delete
from google.appengine.api.datastore import DeleteAsync as _DeleteAsync
from google.appengine.api.datastore import Entity
from google.appengine.api.datastore import Get as _Get
from google.appengine.api.datastore import (IsInTransaction, Key,
                                            NonTransactional)
from google.appengine.api.datastore import Put as _Put
from google.appengine.api.datastore import PutAsync as _PutAsync
from google.appengine.api.datastore import Query, RunInTransaction


def Get(*args, **kwargs):
    return _Get(*args, **kwargs)


def Put(*args, **kwargs):
    return _Put(*args, **kwargs)


def PutAsync(*args, **kwargs):
    return _PutAsync(*args, **kwargs)


def Delete(*args, **kwargs):
    return _Delete(*args, **kwargs)


def DeleteAsync(*args, **kwargs):
    return _DeleteAsync(*args, **kwargs)
