#LIBRARIES
from django.core.cache import cache
#DJANGAE
from djangae.db.utils import get_datastore_kind


DEFAULT_CACHE_TIMEOUT = 10


def cache_entity(model, entity):
    unique_combinations = get_uniques_from_model(model)

    unique_keys = []
    for fields in unique_combinations:
        key_parts = []
        for x in fields:
            if x == model._meta.pk.column and x not in entity:
                value = entity.key().id_or_name()
            else:
                value = entity[x]

            key_parts.append((x, value))

        unique_keys.append(generate_unique_key(model, key_parts))

    for key in unique_keys:
        #logging.error("Caching entity with key %s", key)
        cache.set(key, entity, DEFAULT_CACHE_TIMEOUT)


def uncache_entity(model, entity):
    unique_combinations = get_uniques_from_model(model)

    unique_keys = []
    for fields in unique_combinations:
        key_parts = []
        for x in fields:
            if x == model._meta.pk.column and x not in entity:
                value = entity.key().id_or_name()
            else:
                value = entity[x]
            key_parts.append((x, value))

        key = generate_unique_key(model, key_parts)
        cache.delete(key)


def get_uniques_from_model(model):
    uniques = [ [ model._meta.get_field(y).column for y in x ] for x in model._meta.unique_together ]
    uniques.extend([[x.column] for x in model._meta.fields if x.unique])
    return uniques


def generate_unique_key(model, fields_and_values):
    fields_and_values = sorted(fields_and_values, key=lambda x: x[0]) #Sort by field name

    key = '%s.%s|' % (model._meta.app_label, get_datastore_kind(model))
    key += '|'.join(['%s:%s' % (field, value) for field, value in fields_and_values])
    return key


def get_entity_from_cache(key):
    entity = cache.get(key)
#    if entity:
#        logging.error("Got entity from cache with key %s", key)
    return entity
