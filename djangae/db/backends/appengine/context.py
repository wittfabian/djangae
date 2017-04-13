import copy
import sys

from google.appengine.api import datastore


def key_or_entity_compare(lhs, rhs):
    """
        Returns true if lhs is an entity with a key that matches rhs or
        if lhs is a key which matches rhs, or if lhs is a key which maches
        rhs.key()
    """
    if hasattr(rhs, "key"):
        rhs = rhs.key()

    if hasattr(lhs, "key"):
        lhs = lhs.key()

    return lhs == rhs


class CacheDict(object):
    """
        This is a special dictionary-like object which does the following:

        1. Copys items in and out to prevent storing references
        2. The cache dict is restricted to a maximum size in bytes
        3. Unaccessed entries are removed first
    """

    def __init__(self, max_size_in_bytes=(1024 * 1024 * 32)):
        self.key_priority = []
        self.entries = {}
        self.total_value_size = 0
        self.max_size_in_bytes = max_size_in_bytes

    def _check_size_and_limit(self):
        while self.total_value_size > self.max_size_in_bytes:
            next_key = self.key_priority[-1]
            del self[next_key]

    def __setitem__(self, k, v):
        v = copy.deepcopy(v)
        self.entries[k] = v

        try:
            # If the key already exists, we don't reorder based on a set
            # we only promote keys if they are accessed.
            self.key_priority.index(k)
        except ValueError:
            # Insert new keys in the middle of the priority list, with usage
            # they will either go up or down the list from there
            insert_position = len(self.key_priority) // 2
            self.key_priority.insert(insert_position, k)

        self.total_value_size += sys.getsizeof(v)
        self._check_size_and_limit()

    def __getitem__(self, k):
        v = self.entries[k] # Find the entry

        # Move the key up the key priority
        index = self.key_priority.index(k)
        self.key_priority.pop(index)
        self.key_priority.insert(0, k)
        return copy.deepcopy(v)

    def __delitem__(self, k):
        v = self.entries[k]
        del self.entries[k]
        index = self.key_priority.index(k)
        self.key_priority.pop(index)
        self.total_value_size -= sys.getsizeof(v)

    def __repr__(self):
        return "{%s}" % ", ".join([":".join([repr(k), repr(v)]) for k, v in self.items()])

    def __eq__(self, rhs):
        unshared_items = set(self.items()).difference(set(rhs.items()))
        return len(unshared_items) == 0

    def __contains__(self, k):
        return k in self.entries

    def update(self, other):
        for k, v in other.items():
            self[k] = v

    def __iter__(self):
        return iter(self.key_priority)

    def get(self, k, default=None):
        try:
            return self[k]
        except KeyError:
            return default

    def keys(self):
        """ Returns the keys in priority order (recently used first)"""
        return self.key_priority[:]

    def values(self):
        return self.entries.values()

    def items(self):
        for k in self.keys():
            # Intentionally don't reorganize the key priority if we're iterating
            # that would be *slow* and unlikely to lead to what you want
            yield (k, self.entries[k])

    def get_reversed(self, value, compare_func=None):
        """
            Returns the keys for the specified value.

            If compare_func is specified then it will be called for
            each value in the cache dict with value until compare_func
            returns True
        """
        results = []
        for k, v in self.entries.items():
            if compare_func and compare_func(v, value):
                results.append(k)
            elif v == value:
                results.append(k)
        return results


class ContextCache(object):
    """ Object via which the stack of Context objects and the settings for the context caching are
        accessed. A separate instance of this should exist per thread.
    """
    def __init__(self):
        self.memcache_enabled = True
        self.context_enabled = True
        self.stack = ContextStack()

    def reset(self, keep_disabled_flags=False):
        if datastore.IsInTransaction():
            raise RuntimeError(
                "Clearing the context cache inside a transaction breaks everything, "
                "we can't let you do that"
            )
        self.stack = ContextStack()
        if not keep_disabled_flags:
            self.memcache_enabled = True
            self.context_enabled = True


class Context(object):

    def __init__(self, stack):
        self.cache = CacheDict()
        self._stack = stack

    def apply(self, other):
        self.cache.update(other.cache)

        # We have to delete things that don't exist in the other
        for k in self.cache.keys():
            if k not in other.cache:
                del self.cache[k]

    def cache_entity(self, identifiers, entity, situation):
        assert hasattr(identifiers, "__iter__")

        for identifier in identifiers:
            self.cache[identifier] = entity

    def remove_entity(self, entity_or_key):
        if not isinstance(entity_or_key, datastore.Key):
            entity_or_key = entity_or_key.key()

        for identifier in self.cache.get_reversed(entity_or_key, compare_func=key_or_entity_compare):
            del self.cache[identifier]

    def get_entity(self, identifier):
        return self.cache.get(identifier)

    def get_entity_by_key(self, key):
        try:
            identifier = self.cache.get_reversed(key, compare_func=key_or_entity_compare)[0]
        except IndexError:
            return None
        return self.get_entity(identifier)


class ContextStack(object):
    """
        A stack of contexts. This is used to support in-context
        caches for multi level transactions.
    """

    def __init__(self):
        self.stack = [Context(self)]
        self.staged = []

    def push(self):
        self.stack.append(
            Context(self) # Empty context
        )

    def pop(self, apply_staged=False, clear_staged=False, discard=False):
        """
            apply_staged: pop normally takes the top of the stack and adds it to a FIFO
            queue. By passing apply_staged it will pop to the FIFO queue then apply the
            queue to the top of the stack.

            clear_staged: pop, and then wipe out any staged contexts.

            discard: Ignores the popped entry in the stack, it's just discarded

            The staged queue will be wiped out if the pop makes the size of the stack one,
            regardless of whether you pass clear_staged or not. This is for safety!
        """
        from . import caching


        if not discard:
            self.staged.insert(0, self.stack.pop())
        else:
            self.stack.pop()

        if apply_staged:
            while self.staged:
                to_apply = self.staged.pop()
                keys = [x.key() for x in to_apply.cache.values()]
                if keys:
                    # This assumes that all keys are in the same namespace, which is almost definitely
                    # going to be the case, but it feels a bit dirty
                    namespace = keys[0].namespace() or None
                    caching.remove_entities_from_cache_by_key(
                        keys, namespace=namespace, memcache_only=True
                    )

                self.top.apply(to_apply)

        if clear_staged or len(self.stack) == 1:
            self.staged = []

    @property
    def top(self):
        return self.stack[-1]

    @property
    def size(self):
        return len(self.stack)

    @property
    def staged_count(self):
        return len(self.staged)
