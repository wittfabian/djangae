from .unique_utils import unique_identifiers_from_entity
from django.core.cache import cache

def cache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)

    for identifier in identifiers:
        cache.set(identifier, entity)


def uncache_entity(model, entity):
    identifiers = unique_identifiers_from_entity(model, entity)

    for identifier in identifiers:
        cache.delete(identifier)
