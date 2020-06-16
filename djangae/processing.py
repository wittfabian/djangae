from django.db import router, connections
from django.db.models import Min, Max


def _find_random_keys(queryset, shard_count):
    OVERSAMPLING_FACTOR = 32

    return list(
        queryset.model.objects.order_by("__scatter__").values_list("pk", flat=True)[
            :(shard_count * OVERSAMPLING_FACTOR)
        ]
    )


def _find_key_ranges_for_datastore_queryset(queryset, shard_count):
    """
        This function makes use of the __scatter__ property to return
        a list of key ranges for sharded iteration on the datastore.
    """
    if shard_count > 1:
        # Use the scatter property to generate shard points
        random_keys = _find_random_keys(queryset, shard_count)

        if not random_keys:
            # No random keys? Don't shard
            key_ranges = [(None, None)]
        else:
            random_keys.sort()

            # We have enough random keys to shard things
            if len(random_keys) >= shard_count:
                index_stride = len(random_keys) / float(shard_count)
                split_keys = [random_keys[int(round(index_stride * i))] for i in range(1, shard_count)]
            else:
                split_keys = random_keys

            key_ranges = [(None, split_keys[0])] + [
                (split_keys[i], split_keys[i + 1]) for i in range(len(split_keys) - 1)
            ] + [(split_keys[-1], None)]
    else:
        # Don't shard
        key_ranges = [(None, None)]

    return key_ranges


def _find_key_ranges_for_sql_queryset(queryset, shard_count):
    """
        This function returns a list of key ranges for sharded iteration
        on SQL databases by looking at the min/max primary key values.
    """
    # Can't have more shards than items
    if queryset.count() < shard_count:
        shard_count = queryset.count()

    if shard_count > 1:
        min_max_pks = queryset.aggregate(Min('pk'), Max('pk'))
        pk_range = range(min_max_pks['pk__min'], min_max_pks['pk__max'])

        index_stride = len(pk_range) / float(shard_count)
        split_keys = [pk_range[int(round(index_stride * i))] for i in range(1, shard_count)]

        key_ranges = [(None, split_keys[0])] + [
            (split_keys[i], split_keys[i + 1]) for i in range(len(split_keys) - 1)
        ] + [(split_keys[-1], None)]
    else:
        # Don't shard
        key_ranges = [(None, None)]

    return key_ranges


def find_key_ranges_for_queryset(queryset, shard_count):
    """
        Given a queryset and a number of shard, this function
        returns a list of key ranges for sharded iteration.
    """
    model_db = router.db_for_read(queryset.model)
    conn_engine = connections[model_db].settings_dict.get("ENGINE")

    # Use different methods for finding the key ranges for the datastore and SQL
    if conn_engine in ['djangae.db.backends.appengine', 'gcloudc.db.backends.datastore']:
        return _find_key_ranges_for_datastore_queryset(queryset, shard_count)
    else:
        return _find_key_ranges_for_sql_queryset(queryset, shard_count)
