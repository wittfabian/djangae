import logging

from .unique_utils import unique_identifiers_from_entity
from django.core.cache import cache
from django.dispatch import receiver

from djangae.db.backends.appengine.commands import (
    entity_pre_update,
    entity_post_update,
    entity_post_insert,
    entity_deleted,
    get_pre_execute,
    query_pre_execute
)

__all__ = [ "entity_pre_update_uncache", "entity_post_update_cache", "entity_post_insert_cache", "entity_deleted_uncache" ]


logger = logging.getLogger("djangae")

def cache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)
    logger.debug("Caching entity with key %s and identifiers %s", entity.key(), identifiers)
    cache.set_many({x: entity for x in identifiers})

def uncache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)
    logger.debug("Uncaching entity with key %s and identifiers %s", entity.key(), identifiers)
    for identifier in identifiers:
        cache.delete(identifier)


@receiver(entity_pre_update)
def entity_pre_update_uncache(sender, entity, **kwargs):
    uncache_entity(sender, entity)

@receiver(entity_post_update)
def entity_post_update_cache(sender, entity, **kwargs):
    cache_entity(sender, entity)

@receiver(entity_post_insert)
def entity_post_insert_cache(sender, entity, **kwargs):
    cache_entity(sender, entity)

@receiver(entity_deleted)
def entity_deleted_uncache(sender, entity, **kwargs):
    uncache_entity(sender, entity)