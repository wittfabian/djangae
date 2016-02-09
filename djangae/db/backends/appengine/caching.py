import logging
import threading
import itertools

from google.appengine.api import datastore
from google.appengine.api import memcache
from google.appengine.api.memcache import Client

from django.conf import settings
from djangae.db import utils
from djangae.db.unique_utils import unique_identifiers_from_entity, _format_value_for_identifier
from django.core.cache.backends.base import default_key_func
from djangae.db.backends.appengine.context import ContextStack

logger = logging.getLogger("djangae")

_context = None
_local = threading.local()

def get_context():
    global _context

    if not _context:
        _context = threading.local()

    return _context


CACHE_TIMEOUT_SECONDS = getattr(settings, "DJANGAE_CACHE_TIMEOUT_SECONDS", 60 * 60)
CACHE_ENABLED = getattr(settings, "DJANGAE_CACHE_ENABLED", True)


class CachingSituation:
    DATASTORE_GET = 0
    DATASTORE_PUT = 1
    DATASTORE_GET_PUT = 2 # When we are doing an update

VERSION = 1 # This is so we can invalidate the cache after a backwards incompatible change
# If we ever have to change VERSION it will break our memcache tests (which django.core.cache with VERSION==1)
# in which case we should update them to call memcache.get directly instead

KEY_PREFIX = getattr(settings, "KEY_PREFIX", "") # Use the Django key_prefix


class KeyPrefixedClient(Client):
    """
        This is a special wrapper around some of the GAE memcache functions. It is
        used only for the datastore backend caching.
        Only 3 methods are permitted: get_multi, set_multi_async, and delete_multi_async. This
        ensures that we do things as quickly as possible.
        We have to map keys back and forth to include the prefix and version. That's why some of the
        code may look weird.
    """

    ALLOWED_PROPERTIES = ("get_multi", "set_multi_async", "delete_multi_async")

    def __init__(self, *args, **kwargs):
        self.sync_mode = False
        super(KeyPrefixedClient, self).__init__(*args, **kwargs)

    def set_sync_mode(self, value):
        """
            Enables synchronous RPC calls, useful for testing
        """
        self.sync_mode = bool(value)

    def __getattr__(self, attr):
        if attr not in KeyPrefixedClient.ALLOWED_PROPERTIES and not attr.startswith("__"):
            raise NotImplementedError("Attempted to use non-wrapped memcache API")

        return super(KeyPrefixedClient, self).__getattr__(attr)

    def get_multi(self, keys, key_prefix='', namespace=None, for_cas=False):
        key_mapping = { default_key_func(x, KEY_PREFIX, VERSION): x for x in keys }

        ret = super(KeyPrefixedClient, self).get_multi(
            key_mapping.keys(), key_prefix=key_prefix, namespace=namespace, for_cas=for_cas
        )

        return { key_mapping[k]: v for k, v in ret.iteritems() }

    def set_multi_async(self, mapping, time=0,  key_prefix='', min_compress_len=0, namespace=None, rpc=None):
        mapping = mapping.copy()
        for key in mapping.keys():
            mapping[default_key_func(key, KEY_PREFIX, VERSION)] = mapping[key]
            del mapping[key]

        if self.sync_mode:
            # We don't call up, because set_multi calls set_multi_async
            return memcache.set_multi(
                mapping, time=time, key_prefix=key_prefix,
                min_compress_len=min_compress_len, namespace=namespace
            )
        else:
            return super(KeyPrefixedClient, self).set_multi_async(
                mapping, time=time, key_prefix=key_prefix,
                min_compress_len=min_compress_len, namespace=namespace, rpc=rpc
            )

    def delete_multi_async(self, keys, seconds=0, key_prefix='', namespace=None, rpc=None):
        keys = [ default_key_func(x, KEY_PREFIX, VERSION) for x in keys ]

        if self.sync_mode:
            # We don't call up, because delete_multi calls delete_multi_async
            return memcache.delete_multi(
                keys, seconds=seconds, key_prefix=key_prefix,
                namespace=namespace
            )
        else:
            return super(KeyPrefixedClient, self).delete_multi_async(
                keys, seconds=seconds, key_prefix=key_prefix,
                namespace=namespace, rpc=rpc
            )


def ensure_memcache_client():
    if not hasattr(_local, "memcache"):
        _local.memcache = KeyPrefixedClient()


def ensure_context():
    context = get_context()

    context.memcache_enabled = getattr(context, "memcache_enabled", True)
    context.context_enabled = getattr(context, "context_enabled", True)
    context.stack = context.stack if hasattr(context, "stack") else ContextStack()


def _add_entity_to_memcache(model, mc_key_entity_map):
    ensure_memcache_client()
    _local.memcache.set_multi_async(mc_key_entity_map, time=CACHE_TIMEOUT_SECONDS)


def _get_cache_key_and_model_from_datastore_key(key):
    model = utils.get_model_from_db_table(key.kind())

    if not model:
        # This should never happen.. if it does then we can edit get_model_from_db_table to pass
        # include_deferred=True/included_swapped=True to get_models, whichever makes it better
        raise AssertionError("Unable to locate model for db_table '{}' - item won't be evicted from the cache".format(key.kind()))

    # We build the cache key for the ID of the instance
    cache_key = "|".join(
        [key.kind(), "{}:{}".format(model._meta.pk.column, _format_value_for_identifier(key.id_or_name()))]
    )

    return (cache_key, model)


def _remove_entities_from_memcache_by_key(keys):
    """
        Given an iterable of datastore.Key objects, remove the corresponding entities from memcache.
        Note, if the key of the entity got evicted from the cache, it's possible that stale cache
        entries would be left behind. Remember if you need pure atomicity then use disable_cache() or a
        transaction.
    """
    ensure_memcache_client()

    # Key -> model
    cache_keys = dict(
        _get_cache_key_and_model_from_datastore_key(key) for key in keys
    )
    entities = _local.memcache.get_multi(cache_keys.keys())

    if entities:
        identifiers = [
            unique_identifiers_from_entity(cache_keys[key], entity)
            for key, entity in entities.items()
        ]
        _local.memcache.delete_multi_async(itertools.chain(*identifiers))


def _get_entity_from_memcache(cache_key):
    ensure_memcache_client()
    return _local.memcache.get_multi([cache_key]).get(cache_key)


def _get_entity_from_memcache_by_key(key):
    # We build the cache key for the ID of the instance
    cache_key, _ = _get_cache_key_and_model_from_datastore_key(key)
    return _get_entity_from_memcache(cache_key)


def add_entities_to_cache(model, entities, situation, skip_memcache=False):
    ensure_context()

    # Don't cache on Get if we are inside a transaction, even in the context
    # This is because transactions don't see the current state of the datastore
    # We can still cache in the context on Put() but not in memcache
    if situation == CachingSituation.DATASTORE_GET and datastore.IsInTransaction():
        return

    if situation in (CachingSituation.DATASTORE_PUT, CachingSituation.DATASTORE_GET_PUT) and datastore.IsInTransaction():
        # We have to wipe the entity from memcache
        _remove_entities_from_memcache_by_key([entity.key() for entity in entities if entity.key()])

    identifiers = [
        unique_identifiers_from_entity(model, entity) for entity in entities
    ]

    for ent_identifiers, entity in zip(identifiers, entities):
        get_context().stack.top.cache_entity(ent_identifiers, entity, situation)

    # Only cache in memcache of we are doing a GET (outside a transaction) or PUT (outside a transaction)
    # the exception is GET_PUT - which we do in our own transaction so we have to ignore that!
    if (
        (
            not datastore.IsInTransaction()
            and situation in (CachingSituation.DATASTORE_GET, CachingSituation.DATASTORE_PUT)
        )
        or situation == CachingSituation.DATASTORE_GET_PUT
    ):

        if not skip_memcache:

            mc_key_entity_map = {}
            for ent_identifiers, entity in zip(identifiers, entities):
                mc_key_entity_map.update({
                    identifier: entity for identifier in ent_identifiers
                })
            _add_entity_to_memcache(model, mc_key_entity_map)


def remove_entities_from_cache_by_key(keys, memcache_only=False):
    """
        Given an iterable of datastore.Keys objects, remove the corresponding entities from caches,
        both context and memcache, or just memcache if specified.
    """
    ensure_context()

    if not memcache_only:
        for key in keys:
            identifiers = _context.stack.top.reverse_cache.get(key, [])
            for identifier in identifiers:
                if identifier in _context.stack.top.cache:
                    del _context.stack.top.cache[identifier]

    _remove_entities_from_memcache_by_key(keys)


def get_from_cache_by_key(key):
    """
        Given a datastore.Key, return an
        entity from the context cache, falling back to memcache when possible.
    """

    ensure_context()

    if not CACHE_ENABLED:
        return None

    ret = None
    if _context.context_enabled:
        # It's safe to hit the context cache, because a new one was pushed on the stack at the start of the transaction
        ret = _context.stack.top.get_entity_by_key(key)
        if ret is None and not datastore.IsInTransaction():
            if _context.memcache_enabled:
                ret = _get_entity_from_memcache_by_key(key)
                if ret:
                    # Add back into the context cache
                    add_entities_to_cache(
                        utils.get_model_from_db_table(ret.key().kind()),
                        [ret],
                        CachingSituation.DATASTORE_GET,
                        skip_memcache=True # Don't put in memcache, we just got it from there!
                    )
    elif _context.memcache_enabled and not datastore.IsInTransaction():
        ret = _get_entity_from_memcache_by_key(key)

    return ret


def get_from_cache(unique_identifier):
    """
        Return an entity from the context cache, falling back to memcache when possible
    """

    ensure_context()
    context = get_context()

    if not CACHE_ENABLED:
        return None

    cache_key = unique_identifier
    ret = None
    if context.context_enabled:
        # It's safe to hit the context cache, because a new one was pushed on the stack at the start of the transaction
        ret = context.stack.top.get_entity(cache_key)
        if ret is None and not datastore.IsInTransaction():
            if context.memcache_enabled:
                ret = _get_entity_from_memcache(cache_key)
                if ret:
                    # Add back into the context cache
                    add_entities_to_cache(
                        utils.get_model_from_db_table(ret.key().kind()),
                        [ret],
                        CachingSituation.DATASTORE_GET,
                        skip_memcache=True # Don't put in memcache, we just got it from there!
                    )

    elif context.memcache_enabled and not datastore.IsInTransaction():
        ret = _get_entity_from_memcache(cache_key)

    return ret


def reset_context(keep_disabled_flags=False, *args, **kwargs):
    """
        Called at the beginning and end of each request, resets the thread local
        context. If you pass keep_disabled_flags=True the memcache_enabled and context_enabled
        flags will be preserved, this is really only useful for testing.
    """

    context = get_context()

    memcache_enabled = getattr(context, "memcache_enabled", True)
    context_enabled = getattr(context, "context_enabled", True)

    context.memcache_enabled = True
    context.context_enabled = True
    context.stack = ContextStack()

    if keep_disabled_flags:
        context.memcache_enabled = memcache_enabled
        context.context_enabled = context_enabled
