import logging
import threading

from google.appengine.api import datastore

from django.core.cache import cache
from django.core.signals import request_finished, request_started
from django.dispatch import receiver
from djangae.db import utils
from djangae.db.unique_utils import unique_identifiers_from_entity, _format_value_for_identifier
from djangae.db.backends.appengine.context import ContextStack

logger = logging.getLogger("djangae")

_context = threading.local()

class CachingSituation:
    DATASTORE_GET = 0
    DATASTORE_PUT = 1
    DATASTORE_GET_PUT = 2 # When we are doing an update

def ensure_context():
    if not hasattr(_context, "memcache_enabled"):
        _context.memcache_enabled = True

    if not hasattr(_context, "context_enabled"):
        _context.context_enabled = True

    if not hasattr(_context, "stack"):
        _context.stack = ContextStack()


def _add_entity_to_memcache(model, entity, identifiers):
    cache.set_many({ x: entity for x in identifiers})


def _remove_entity_from_memcache_by_key(key):
    """
        Note, if the key of the entity got evicted from the cache, it's possible that stale cache
        entries would be left behind. Remember if you need pure atomicity then use disable_cache() or a
        transaction.
    """
    model = utils.get_model_from_db_table(key.kind())

    if not model:
        # This should never happen.. if it does then we can edit get_model_from_db_table to pass
        # include_deferred=True/included_swapped=True to get_models, whichever makes it better
        logging.warning("Unable to locate model for db_table '{}' - item won't be evicted from the cache".format(key.kind()))
        return

    # We build the cache key for the ID of the instance
    cache_key =  "|".join([key.kind(), "{}:{}".format(model._meta.pk.column,  _format_value_for_identifier(key.id_or_name()))])

    entity = cache.get(cache_key)

    if entity:
        identifiers = unique_identifiers_from_entity(model, entity)
        cache.delete_many(identifiers)


def _get_entity_from_memcache(identifier):
    return cache.get(identifier)


def add_entity_to_cache(model, entity, situation):
    ensure_context()

    identifiers = unique_identifiers_from_entity(model, entity)

    # Don't cache on Get if we are inside a transaction, even in the context
    # This is because transactions don't see the current state of the datastore
    # We can still cache in the context on Put() but not in memcache
    if situation == CachingSituation.DATASTORE_GET and datastore.IsInTransaction():
        return

    if situation in (CachingSituation.DATASTORE_PUT, CachingSituation.DATASTORE_GET_PUT) and datastore.IsInTransaction():
        # We have to wipe the entity from memcache
        if entity.key():
            _remove_entity_from_memcache_by_key(entity.key())

    _context.stack.top.cache_entity(identifiers, entity, situation)

    # Only cache in memcache of we are doing a GET (outside a transaction) or PUT (outside a transaction)
    # the exception is GET_PUT - which we do in our own transaction so we have to ignore that!
    if (not datastore.IsInTransaction() and situation in (CachingSituation.DATASTORE_GET, CachingSituation.DATASTORE_PUT)) or \
            situation == CachingSituation.DATASTORE_GET_PUT:

        _add_entity_to_memcache(model, entity, identifiers)


def remove_entity_from_cache(entity):
    key = entity.key()
    remove_entity_from_cache_by_key(key)


def remove_entity_from_cache_by_key(key):
    ensure_context()

    for identifier in _context.stack.top.reverse_cache.get(key, []):
        if identifier in _context.stack.top.cache:
            del _context.stack.top.cache[identifier]

    _remove_entity_from_memcache_by_key(key)

def get_from_cache_by_key(key):
    ensure_context()

    ret = None
    if _context.context_enabled:
        ret = _context.stack.top.get_entity_by_key(key)
        if ret is None:
            if _context.memcache_enabled:
                pass #FIXME: do memcache thing
    elif _context.memcache_enabled:
        pass #FIXME: do memcache thing

    return ret

def get_from_cache(unique_identifier):
    ensure_context()

    ret = None
    if _context.context_enabled:
        ret = _context.stack.top.get_entity(unique_identifier)
        if ret is None:
            if _context.memcache_enabled:
                ret = _get_entity_from_memcache(unique_identifier)
    elif _context.memcache_enabled:
        ret = _get_entity_from_memcache(unique_identifier)

    return ret

@receiver(request_finished)
@receiver(request_started)
def clear_context_cache(*args, **kwargs):
    global _context
    _context = threading.local()
    ensure_context()
