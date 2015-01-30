import logging
import threading

from google.appengine.api import datastore

from django.conf import settings
from django.core.cache import cache
from django.core.signals import request_finished, request_started
from django.dispatch import receiver
from djangae.db import utils
from djangae.db.unique_utils import unique_identifiers_from_entity, _format_value_for_identifier
from djangae.db.backends.appengine.context import ContextStack

logger = logging.getLogger("djangae")

_context = threading.local()

CACHE_TIMEOUT_SECONDS = getattr(settings, "DJANGAE_CACHE_TIMEOUT_SECONDS", 60 * 60)
CACHE_ENABLED = getattr(settings, "DJANGAE_CACHE_ENABLED", True)


class CachingSituation:
    DATASTORE_GET = 0
    DATASTORE_PUT = 1
    DATASTORE_GET_PUT = 2 # When we are doing an update


def ensure_context():
    _context.memcache_enabled = getattr(_context, "memcache_enabled", True)
    _context.context_enabled = getattr(_context, "context_enabled", True)
    _context.stack = _context.stack if hasattr(_context, "stack") else ContextStack()


def _add_entity_to_memcache(model, entity, identifiers):
    cache.set_many({ x: entity for x in identifiers}, timeout=CACHE_TIMEOUT_SECONDS)


def _get_cache_key_and_model_from_datastore_key(key):
    model = utils.get_model_from_db_table(key.kind())

    if not model:
        # This should never happen.. if it does then we can edit get_model_from_db_table to pass
        # include_deferred=True/included_swapped=True to get_models, whichever makes it better
        raise AssertionError("Unable to locate model for db_table '{}' - item won't be evicted from the cache".format(key.kind()))

    # We build the cache key for the ID of the instance
    cache_key =  "|".join([key.kind(), "{}:{}".format(model._meta.pk.column,  _format_value_for_identifier(key.id_or_name()))])

    return (cache_key, model)


def _remove_entity_from_memcache_by_key(key):
    """
        Note, if the key of the entity got evicted from the cache, it's possible that stale cache
        entries would be left behind. Remember if you need pure atomicity then use disable_cache() or a
        transaction.
    """

    cache_key, model = _get_cache_key_and_model_from_datastore_key(key)
    entity = cache.get(cache_key)

    if entity:
        identifiers = unique_identifiers_from_entity(model, entity)
        cache.delete_many(identifiers)


def _get_entity_from_memcache(identifier):
    return cache.get(identifier)


def _get_entity_from_memcache_by_key(key):
    # We build the cache key for the ID of the instance
    cache_key, _ = _get_cache_key_and_model_from_datastore_key(key)
    return cache.get(cache_key)


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
    """
        Removes an entity from all caches (both context and memcache)
    """
    ensure_context()

    for identifier in _context.stack.top.reverse_cache.get(key, []):
        if identifier in _context.stack.top.cache:
            del _context.stack.top.cache[identifier]

    _remove_entity_from_memcache_by_key(key)


def get_from_cache_by_key(key):
    """
        Return an entity from the context cache, falling back to memcache when possible
    """

    ensure_context()

    if not CACHE_ENABLED:
        return None

    ret = None
    if _context.context_enabled:
        ret = _context.stack.top.get_entity_by_key(key)
        if ret is None and not datastore.IsInTransaction():
            if _context.memcache_enabled:
                ret = _get_entity_from_memcache_by_key(key)
    elif _context.memcache_enabled and not datastore.IsInTransaction():
        ret = _get_entity_from_memcache_by_key(key)

    return ret


def get_from_cache(unique_identifier):
    """
        Return an entity from the context cache, falling back to memcache when possible
    """

    ensure_context()

    if not CACHE_ENABLED:
        return None

    ret = None
    if _context.context_enabled:
        ret = _context.stack.top.get_entity(unique_identifier)
        if ret is None and not datastore.IsInTransaction():
            if _context.memcache_enabled:
                ret = _get_entity_from_memcache(unique_identifier)
    elif _context.memcache_enabled and not datastore.IsInTransaction():
        ret = _get_entity_from_memcache(unique_identifier)

    return ret


@receiver(request_finished)
@receiver(request_started)
def reset_context(keep_disabled_flags=False, *args, **kwargs):
    """
        Called at the beginning and end of each request, resets the thread local
        context. If you pass keep_disabled_flags=True the memcache_enabled and context_enabled
        flags will be preserved, this is really only useful for testing.
    """

    memcache_enabled = getattr(_context, "memcache_enabled", True)
    context_enabled = getattr(_context, "context_enabled", True)

    for attr in ("stack", "memcache_enabled", "context_enabled"):
        if hasattr(_context, attr):
            delattr(_context, attr)

    ensure_context()

    if keep_disabled_flags:
        _context.memcache_enabled = memcache_enabled
        _context.context_enabled = context_enabled
