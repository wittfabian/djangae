# This is essentially a slimmed down mapreduce. There are some differences with the sharding logic
# and the whole thing leverages defer and there's no reducing, just mapping.

# If you're wondering why we're not using MR here...
# 1. We don't want a hard dependency on it and migrations are core (unlike stuff in contrib)
# 2. MR is massive overkill for what we're doing here

import copy
import cPickle
import logging

from datetime import datetime
from django.conf import settings
from google.appengine.api import datastore, datastore_errors
from google.appengine.api.taskqueue.taskqueue import _DEFAULT_QUEUE
from google.appengine.ext import deferred
from google.appengine.runtime import DeadlineExceededError


class Redefer(Exception):
    """ Custom exception class to allow triggering of the re-deferring of a processing task. """
    pass


def _mid_string(string1, string2):
    """ Given 2 unicode strings, return the string that is alphabetically half way between them. """
    # Put the strings in order, so the lowest one is lhs
    lhs = min(string1, string2)
    rhs = max(string1, string2)
    # Pad out the shorter string so that they're both the same length
    longest_length = max(len(lhs), len(rhs))
    lhs = lhs.ljust(longest_length, "\0")
    # For each position in the strings, find the mid character
    mid = []
    for l, r in zip(lhs, rhs):
        l = ord(l)
        r = ord(r)
        mid.append(l + (r - l) / 2)
    # Note that some of the numbers might be invalid unicode values, but for the purposes of
    # filtering Datastore keys it doesn't matter
    result = u"".join([unichr(x) for x in mid])
    # Strings starting with a double underscore are not valid Datastore keys
    if result.startswith(u"__"):
        result = u"_`" + result[2:]
    return result


def _next_string(string):
    """ Given a string (or unicode), return the alphabetically next string. """
    # Note that in python 2 at least, unicode is 16 bit, and therefore some characters (e.g. emoji)
    # are encoded as 2 characters, so when we slice the last "character" off the string we're
    # actually getting half a character, and then when we increment it we're possibly creating an
    # invalid character, but for the purpose of ordering Datastore keys it shouldn't matter
    try:
        # Try to increment the last character by 1
        return string[:-1] + unichr(ord(string[-1]) + 1)
    except ValueError:
        # If the last character was already the highest possible unicode value, then instead add
        # another character to the string
        return string + unichr(1)


def _next_key(key):
    """
        Given a key, this returns key + 1. In the case of key names
        we simply calculate the next alphabetical key
    """
    val = key.id_or_name()
    if isinstance(val, basestring):
        return datastore.Key.from_path(
            key.kind(),
            _next_string(val),
            namespace=key.namespace()
        )
    else:
        return datastore.Key.from_path(
            key.kind(),
            val + 1,
            namespace=key.namespace()
        )


def _mid_key(key1, key2):
    """
        Given two keys, this function returns the key mid-way between them
        - this needs some thought on how to do this with strings
    """
    key1_val = key1.id_or_name()
    key2_val = key2.id_or_name()

    if type(key1_val) != type(key2_val):
        raise NotImplementedError(
            "Sharding of entities with mixed integer and string types is not yet supported."
        )

    if isinstance(key1_val, basestring):
        mid_id_or_name = _mid_string(key1_val, key2_val)
    else:
        mid_id_or_name = key1_val + ((key2_val - key1_val) // 2)

    return datastore.Key.from_path(
        key1.kind(),
        mid_id_or_name,
        namespace=key1.namespace()
    )


def _get_range(key1, key2):
    """ Given 2 Datastore keys, return the range that their IDs span.
        E.g. if the IDs are 7 and 100, then the range is 93.
        Works for string-based keys as well, but returns a string representation of the difference.
    """
    val1 = key1.id_or_name()
    val2 = key2.id_or_name()
    if type(val1) != type(val2):
        raise Exception("Cannot calculate range between keys of different types.")
    if isinstance(val1, (int, long)):
        return val2 - val1
    # Otherwise, the values are strings...
    # Put the strings in order, so the lowest one is lhs
    lhs = min(val1, val2)
    rhs = max(val1, val2)
    # Pad out the shorter string so that they're both the same length
    longest_length = max(len(lhs), len(rhs))
    lhs = lhs.ljust(longest_length, "\0")
    # For each position in the strings, find the difference
    diffs = []
    for l, r in zip(lhs, rhs):
        diffs.append(ord(r) - ord(l))
    # We return this "difference" as a string
    return u"".join([unichr(x) for x in diffs])


def _generate_shards(keys, shard_count):
    """
        Given a set of keys with:
        - The first key being the lowest in the range
        - The last key being the highest in the range
        - The other keys being evenly distributed (e.g. __scatter__)

        This function returns a list of [start_key, end_key] shards to cover the range

        This may not return shard_count shards if there aren't enough split points
    """
    keys = sorted(keys)  # Ensure the keys are sorted

    # Special case single key
    if shard_count == 1:
        return [[keys[0], keys[-1]]]
    elif shard_count < len(keys):
        # If there are more split point keys than we need then We have to calculate a
        # stride to skip some of the split point keys to return shard_count shards
        index_stride = len(keys) / float(shard_count)
        keys = [keys[int(round(index_stride * i))] for i in range(1, shard_count)]

    shards = []
    for i in xrange(len(keys) - 1):
        shards.append([keys[i], keys[i + 1]])

    return shards


def _find_largest_shard(shards):
    """
        Given a list of shards, where each shard is a pair of (lowest_key, highest_key),
        return the shard with the largest ID range
    """
    largest_shard = None
    range_of_largest_shard = None

    for shard in shards:
        if largest_shard is None:
            largest_shard = shard
            range_of_largest_shard = _get_range(shard[0], shard[1])
        else:
            this_range = _get_range(shard[0], shard[1])
            if this_range > range_of_largest_shard:
                largest_shard = shard
                range_of_largest_shard = _get_range(shard[0], shard[1])

    return largest_shard


def shard_query(query, shard_count):
    """ Given a datastore.Query object and a number of shards, return a list of shards where each
        shard is a pair of (low_key, high_key).
        May return fewer than `shard_count` shards in cases where there aren't many entities.
    """
    OVERSAMPLING_MULTIPLIER = 32  # This value is used in Mapreduce

    try:
        query.Order("__key__")
        min_id = query.Run().next().key()

        query.Order(("__key__", query.DESCENDING))
        max_id = query.Run().next().key()
    except StopIteration:
        # No objects, so no shards
        return []

    query.Order("__scatter__")  # Order by the scatter property

    # Get random keys to shard on
    keys = [x.key() for x in query.Get(shard_count * OVERSAMPLING_MULTIPLIER)]
    keys.sort()

    if not keys:  # If no keys...
        # Shard on the upper and lower PKs in the query this is *not* efficient
        keys = [min_id, max_id]
    else:
        if keys[0] != min_id:
            keys.insert(0, min_id)

        if keys[-1] != max_id or min_id == max_id:
            keys.append(max_id)

    # We generate as many shards as we can, but if it's not enough then we
    # iterate, splitting the largest shard into two shards until either:
    # - we hit the desired shard count
    # - we can't subdivide anymore
    shards = _generate_shards(keys, shard_count)
    while True:
        if len(shards) >= shard_count:
            break

        # If we don't have enough shards, divide the largest key range until we have enough
        largest_shard = _find_largest_shard(shards)

        # OK we can't shard anymore, just bail
        if largest_shard[0] == largest_shard[1]:
            break

        left_shard = [
            largest_shard[0],
            _mid_key(largest_shard[0], largest_shard[1])
        ]

        right_shard = [
            _next_key(_mid_key(largest_shard[0], largest_shard[1])),
            largest_shard[1]
        ]

        # We already have these shards, just give up now
        if left_shard in shards and right_shard in shards:
            break

        shards.remove(largest_shard)
        if left_shard not in shards:
            shards.append(left_shard)

        if right_shard not in shards:
            shards.append(right_shard)
        shards.sort()

    assert len(shards) <= shard_count

    # We shift the end keys in each shard by one, so we can
    # do a >= && < query
    for shard in shards:
        shard[1] = _next_key(shard[1])

    return shards


class ShardedTaskMarker(datastore.Entity):
    """ Manages the running of an operation over the entities of a query using multiple processing
        tasks.  Stores details of the current state on itself as an Entity in the Datastore.
    """
    KIND = "_djangae_migration_task"

    QUEUED_KEY = "shards_queued"
    RUNNING_KEY = "shards_running"
    FINISHED_KEY = "shards_finished"

    def __init__(self, identifier, query, *args, **kwargs):
        kwargs["kind"] = self.KIND
        kwargs["name"] = identifier

        super(ShardedTaskMarker, self).__init__(*args, **kwargs)

        self[ShardedTaskMarker.QUEUED_KEY] = []
        self[ShardedTaskMarker.RUNNING_KEY] = []
        self[ShardedTaskMarker.FINISHED_KEY] = []
        self["time_started"] = None
        self["time_finished"] = None
        self["query"] = cPickle.dumps(query)
        self["is_finished"] = False

    @classmethod
    def get_key(cls, identifier, namespace):
        return datastore.Key.from_path(
            cls.KIND,
            identifier,
            namespace=namespace
        )

    def put(self, *args, **kwargs):
        if not self["is_finished"]:
            # If we aren't finished, see if we are now
            # This if-statement is important because if a task had no shards
            # it would be 'finished' immediately so we don't want to incorrectly
            # set it to False when we save if we manually set it to True
            self["is_finished"] = bool(
                not self[ShardedTaskMarker.QUEUED_KEY] and
                not self[ShardedTaskMarker.RUNNING_KEY] and
                self[ShardedTaskMarker.FINISHED_KEY]
            )

            if self["is_finished"]:
                self["time_finished"] = datetime.utcnow()

        datastore.Put(self)

    def run_shard(
        self, original_query, shard, operation, operation_method=None, offset=0,
        entities_per_task=None, queue=_DEFAULT_QUEUE
    ):
        """ Given a datastore.Query which does not have any high/low bounds on it, apply the bounds
            of the given shard (which is a pair of keys), and run either the given `operation`
            (if it's a function) or the given method of the given operation (if it's an object) on
            each entity that the query returns, starting at entity `offset`, and redeferring every
            `entities_per_task` entities to avoid hitting DeadlineExceededError.
            Tries (but does not guarantee) to avoid processing the same entity more than once.
        """
        entities_per_task = entities_per_task or getattr(
            settings, "DJANGAE_MIGRATION_DEFAULT_ENTITIES_PER_TASK", 100
        )
        if operation_method:
            function = getattr(operation, operation_method)
        else:
            function = operation

        marker = datastore.Get(self.key())
        if cPickle.dumps(shard) not in marker[ShardedTaskMarker.RUNNING_KEY]:
            return

        # Copy the query so that we can re-defer the original, unadulterated version, because once
        # we've applied limits and ordering to the query it causes pickle errors with defer.
        query = copy.deepcopy(original_query)
        query.Order("__key__")
        query["__key__ >="] = shard[0]
        query["__key__ <"] = shard[1]

        num_entities_processed = 0
        try:
            results = query.Run(offset=offset, limit=entities_per_task)
            for entity in results:
                function(entity)
                num_entities_processed += 1
                if num_entities_processed >= entities_per_task:
                    raise Redefer()
        except (DeadlineExceededError, Redefer):
            # By keeping track of how many entities we've processed, we can (hopefully) avoid
            # re-processing entities if we hit DeadlineExceededError by redeferring with the
            # incremented offset.  But note that if we get crushed by the HARD DeadlineExceededError
            # before we can redefer, then the whole task will retry and so entities will get
            # processed twice.
            deferred.defer(
                self.run_shard,
                original_query,
                shard,
                operation,
                operation_method,
                offset=offset+num_entities_processed,
                entities_per_task=entities_per_task,
                # Defer this task onto the correct queue (with `_queue`), passing the `queue`
                # parameter back to the function again so that it can do the same next time
                queue=queue,
                _queue=queue,
            )
            return  # This is important!

        # Once we've run the operation on all the entities, mark the shard as done
        def txn():
            pickled_shard = cPickle.dumps(shard)
            marker = datastore.Get(self.key())
            marker.__class__ = ShardedTaskMarker
            marker[ShardedTaskMarker.RUNNING_KEY].remove(pickled_shard)
            marker[ShardedTaskMarker.FINISHED_KEY].append(pickled_shard)
            marker.put()

        datastore.RunInTransaction(txn)

    def begin_processing(self, operation, operation_method, entities_per_task, queue):
        BATCH_SIZE = 3

        # Unpickle the source query
        query = cPickle.loads(str(self["query"]))

        def txn():
            try:
                marker = datastore.Get(self.key())
                marker.__class__ = ShardedTaskMarker

                queued_shards = marker[ShardedTaskMarker.QUEUED_KEY]
                processing_shards = marker[ShardedTaskMarker.RUNNING_KEY]
                queued_count = len(queued_shards)

                for j in xrange(min(BATCH_SIZE, queued_count)):
                    pickled_shard = queued_shards.pop()
                    processing_shards.append(pickled_shard)
                    shard = cPickle.loads(str(pickled_shard))
                    deferred.defer(
                        self.run_shard,
                        query,
                        shard,
                        operation,
                        operation_method,
                        entities_per_task=entities_per_task,
                        # Defer this task onto the correct queue with `_queue`, passing the `queue`
                        # parameter back to the function again so that it can do the same next time
                        queue=queue,
                        _queue=queue,
                        _transactional=True,
                    )

                marker.put()
            except datastore_errors.EntityNotFoundError:
                logging.error(
                    "Unable to start task %s as marker is missing",
                    self.key().id_or_name()
                )
                return

        # Reload the marker (non-transactionally) and defer the shards in batches
        # transactionally. If this task fails somewhere, it will resume where it left off
        marker = datastore.Get(self.key())
        for i in xrange(0, len(marker[ShardedTaskMarker.QUEUED_KEY]), BATCH_SIZE):
            datastore.RunInTransaction(txn)


def start_mapping(
    identifier, query, operation, operation_method=None, shard_count=None,
    entities_per_task=None, queue=None
):
    """ This must *transactionally* defer a task which will call `operation._wrapped_map_entity` on
        all entities of the given `kind` in the given `namespace` and will then transactionally
        update the entity of the given `task_marker_key_key` with `is_finished=True` after all
        entities have been mapped.
    """
    shard_count = shard_count or getattr(settings, "DJANGAE_MIGRATION_DEFAULT_SHARD_COUNT", 32)
    shards_to_run = shard_query(query, shard_count)
    queue = queue or getattr(settings, "DJANGAE_MIGRATION_DEFAULT_QUEUE", _DEFAULT_QUEUE)

    def txn(shards):
        marker_key = ShardedTaskMarker.get_key(identifier, query._Query__namespace)
        try:
            datastore.Get(marker_key)

            # If the marker already exists, don't do anything - just return
            return
        except datastore_errors.EntityNotFoundError:
            pass

        marker = ShardedTaskMarker(identifier, query, namespace=query._Query__namespace)

        if shards:
            for shard in shards:
                marker["shards_queued"].append(cPickle.dumps(shard))
        else:
            # No shards, then there is nothing to do!
            marker["is_finished"] = True
        marker["time_started"] = datetime.utcnow()
        marker.put()
        if not marker["is_finished"]:
            deferred.defer(
                marker.begin_processing, operation, operation_method, entities_per_task, queue,
                _transactional=True, _queue=queue
            )

        return marker_key

    return datastore.RunInTransaction(txn, shards_to_run)


def mapper_exists(identifier, namespace):
    """
        Returns True if the mapper exists, False otherwise
    """
    try:
        datastore.Get(ShardedTaskMarker.get_key(identifier, namespace))
        return True
    except datastore_errors.EntityNotFoundError:
        return False


def is_mapper_finished(identifier, namespace):
    """
        Returns True if the mapper exists, and it's not running.
    """
    return mapper_exists(identifier, namespace) and not is_mapper_running(identifier, namespace)


def is_mapper_running(identifier, namespace):
    """
        Returns True if the mapper exists, but it's not finished
    """
    try:
        marker = datastore.Get(ShardedTaskMarker.get_key(identifier, namespace))
        return not marker["is_finished"]
    except datastore_errors.EntityNotFoundError:
        return False
