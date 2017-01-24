# Skeleton layout of what the mapping library that we use will need to do


###################################################################################################
#
#
#                 THIS IS NOT "REAL" CODE.  REPLACE WITH A PROPER MAPPING LIBRARY!
#
#
#
###################################################################################################


from django.utils import timezone
from google.appengine.api import datastore
from google.appengine.ext import deferred


def _generate_shards(keys, shard_count):
    keys = sorted(keys) # Ensure the keys are sorted

    # Special case single key
    if shard_count == 1:
        return [[keys[0], keys[-1]]]
    elif shard_count < len(keys):
        index_stride = len(keys) / float(shard_count)
        keys = [keys[int(round(index_stride * i))] for i in range(1, shard_count)]

    shards = []
    for i in xrange(len(keys) - 1):
        shards.append([keys[i], keys[i + 1]])

    return shards


def _find_largest_shard(shards):
    """
        Given a list of shards, find the one with the largest ID range
    """
    largest_shard = None

    for shard in shards:
        if largest_shard is None:
            largest_shard = shard
        else:
            current_range = largest_shard[1].id_or_name() - largest_shard[0].id_or_name()
            this_range = shard[1].id_or_name() - shard[0].id_or_name()
            if this_range > current_range:
                largest_shard = shard

    return largest_shard


def shard_query(query, shard_count):
    OVERSAMPLING_MULTIPLIER = 32 # This value is used in Mapreduce

    try:
        query.Order("__key__")
        min_id = query.Run().next().key()

        query.Order(("__key__", query.DESCENDING))
        max_id = query.Run().next().key()
    except StopIteration:
        # No objects, so no shards
        return []

    query.Order("__scatter__") # Order by the scatter property

    # Get random keys to shard on
    keys = [ x.key() for x in query.Get(shard_count * OVERSAMPLING_MULTIPLIER) ]
    if not keys: # If no keys...
        # Shard on the upper and lower PKs in the query this is *not* efficient
        keys = [min_id, max_id]
    else:
        if keys[0] != min_id:
            keys.insert(0, min_id)

        if keys[-1] != max_id:
            keys.append(max_id)

    keys.sort()

    shards = _generate_shards(keys, shard_count)
    while True:
        if len(shards) >= shard_count:
            break

        # If we don't have enough shards, divide the largest key range until we have enough
        largest_shard = _find_largest_shard(shards)
        half_range = (largest_shard[1].id_or_name() - (largest_shard[0].id_or_name() or 0)) / 2

        # OK we can't shard anymore, just bail
        if half_range == 0:
            break

        kind = min_id.kind()
        namespace = min_id.namespace()

        left_shard = [
            datastore.Key.from_path(kind, largest_shard[0].id_or_name(), namespace=namespace),
            datastore.Key.from_path(kind, largest_shard[0].id_or_name() + half_range, namespace=namespace)
        ]

        right_shard = [
            datastore.Key.from_path(kind, largest_shard[0].id_or_name() + half_range, namespace=namespace),
            datastore.Key.from_path(kind, largest_shard[1].id_or_name(), namespace=namespace)
        ]

        insertion_point = shards.index(largest_shard)
        shards[insertion_point] = left_shard
        shards.insert(insertion_point + 1, right_shard)

    assert len(shards) <= shard_count

    return shards


def start_mapping(task_marker_key, kind, namespace, operation):
    """ This must *transactionally* defer a task which will call `operation._wrapped_map_entity` on
        all entities of the given `kind` in the given `namespace` and will then transactionally
        update the entity of the given `task_marker_key_key` with `is_finished=True` after all
        entities have been mapped.
    """
    # The reason for taking an `operation` object and calling `_wrapped_map_entity` on it is that
    # instance methods cannot be pickled, but we can pickle the object and then call a method on it
    deferred.defer(do_mapping, task_marker_key, kind, namespace, operation, _transactional=True)


def do_mapping(task_marker_key, kind, namespace, operation):

    method = getattr(operation, '_wrapped_map_entity')

    results = datastore.Query(kind, namespace=namespace).Run()
    for entity in results:
        method(entity)

    def finish(task_marker_key):
        task_marker = datastore.Get(task_marker_key)
        task_marker['finish_time'] = timezone.now()
        task_marker['is_finished'] = True
        datastore.Put(task_marker)

    datastore.RunInTransaction(finish, task_marker_key)
