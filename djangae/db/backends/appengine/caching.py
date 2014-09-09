import logging
import threading

from django.core.signals import request_finished
from django.dispatch import receiver

from djangae.db.unique_utils import unique_identifiers_from_entity
from django.core.cache import cache

logger = logging.getLogger("djangae")

context = threading.local()

def cache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)
    logger.debug("Caching entity with key %s and identifiers %s", entity.key(), identifiers)
    cache.set_many({x: entity for x in identifiers})

def uncache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)
    logger.debug("Uncaching entity with key %s and identifiers %s", entity.key(), identifiers)
    for identifier in identifiers:
        cache.delete(identifier)


@receiver(request_finished)
def clear_context_cache(*args, **kwargs):
    global context_cache
    context.cache = {}