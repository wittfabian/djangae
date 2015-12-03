import random

from django.core.exceptions import ImproperlyConfigured
from google.appengine.datastore.datastore_rpc import BaseConnection
from google.appengine.datastore.datastore_stub_util import _MAX_EG_PER_TXN

from djangae.fields.related import (
    RelatedSetField,
    RelatedIteratorManagerBase,
    ReverseRelatedObjectsDescriptor,
)
from djangae.models import CounterShard
from djangae.db import transaction


MAX_ENTITIES_PER_GET = BaseConnection.MAX_GET_KEYS

# If the number of shards plus 1 (for the object to which they belong) is <= the max entity groups per
# transaction then we can do the populate() operation in a single transaction, which is nice, hence:
DEFAULT_SHARD_COUNT = MAX_SHARDS_PER_TRANSACTION = _MAX_EG_PER_TXN - 1


class RelatedShardManager(RelatedIteratorManagerBase, CounterShard._default_manager.__class__):
    """ This is what is given to you when you access the field attribute on an instance.  It's a
        model manager with the usual queryset methods (the same as for RelatedSetField) but with
        the additional increment()/decrement()/reset() methods for the counting.
    """

    def increment(self, step=1):
        if step < 0:
            raise ValueError("Tried to increment with a negative number, use decrement instead")

        self._update_or_create_shard(step)

    def decrement(self, step=1):
        if step < 0:
            raise ValueError("Tried to decrement with a negative number, use increment instead")
        self._update_or_create_shard(-step)

    def value(self):
        """ Calcuate the aggregated sum of all the shard values. """
        shards = self.all().values_list('count', flat=True)
        return sum(shards)

    def reset(self):
        """ Reset the counter to 0. """
        # This is not transactional because (1) that wouldn't work with > 24 shards, and (2) if
        # there are other threads doing increments/decrements at the same time then it doesn't make
        # any difference if they happen before or after our increment/decrement anyway.
        value = self.value()
        if value > 0:
            self.decrement(value)
        elif value < 0:
            self.increment(abs(value))

    def clear(self):
        # Override the default `clear` method of the parent class, as that only clears the list of
        # PKs but doesn't delete the related objects.  We want to delete the objects (shards) as well.
        self.reset()

    def populate(self):
        """ Create all the CounterShard objects which will be used by this field. Useful to prevent
            additional saves being caused when you call increment() or decrement() due to having to
            update the list of shard PKs on the instance.
        """
        total_to_create = self.field.shard_count - len(self)
        while total_to_create:
            with transaction.atomic(xg=True):
                # We must re-fetch the instance to ensure that we do this atomically, but we must
                # also update self.instance so that the calling code which is referencing
                # self.instance also gets the updated list of shard PKs
                new_instance = self.instance._default_manager.get(pk=self.instance.pk)
                new_instance_shard_pks = getattr(new_instance, self.field.attname, set())
                # Re-check / update the number to create based on the refreshed instance from the DB
                total_to_create = self.field.shard_count - len(new_instance_shard_pks)
                num_to_create = min(total_to_create, MAX_SHARDS_PER_TRANSACTION)

                new_shard_pks = set()
                for x in xrange(num_to_create):
                    new_shard_pks.add(self._create_shard(count=0).pk)

                new_instance_shard_pks.update(new_shard_pks)
                setattr(self.instance, self.field.attname, new_instance_shard_pks)
                new_instance.save()
                total_to_create -= num_to_create

    def _update_or_create_shard(self, step):
        """ Find or create a random shard and alter its `count` by the given step. """
        shard_index = random.randint(0, self.field.shard_count - 1)
        # Converting the set to a list introduces some randomness in the ordering, but that's fine
        shard_pks = list(self.field.value_from_object(self.instance)) # needs to be indexable
        try:
            shard_pk = shard_pks[shard_index]
        except IndexError:
            # We don't have this many shards yet, so create a new one
            with transaction.atomic(xg=True):
                # We must re-fetch the instance to ensure that we do this atomically, but we must
                # also update self.instance so that the calling code which is referencing
                # self.instance also gets the updated list of shard PKs
                new_shard = self._create_shard(count=step)
                new_instance = self.instance._default_manager.get(pk=self.instance.pk)
                new_instance_shard_pks = getattr(new_instance, self.field.attname, set())
                new_instance_shard_pks.add(new_shard.pk)
                setattr(self.instance, self.field.attname, new_instance_shard_pks)
                new_instance.save()
        else:
            with transaction.atomic():
                shard = CounterShard.objects.get(pk=shard_pk)
                shard.count += step
                shard.save()

    def _create_shard(self, count):
        return CounterShard.objects.create(
            count=count, label="%s.%s" % (self.instance._meta.db_table, self.field.name)
        )


class ReverseRelatedShardsDescriptor(ReverseRelatedObjectsDescriptor):
    """ Subclass of the RelatedSetField's ReverseRelatedObjectsDescriptor which overrides the
        related manager class and prevents setting of the field value directly.
    """
    @property
    def related_manager_cls(self):
        return RelatedShardManager

    def __set__(self, instance, value):
        raise AttributeError(
            "You should not try to set the value of a ShardedCounterField manually. "
            "Use the increment() or decrement() methods."
        )


class ShardedCounterField(RelatedSetField):

    def __init__(self, shard_count=DEFAULT_SHARD_COUNT, *args, **kwargs):
        # Note that by removing the related_name by default we avoid reverse name clashes caused by
        # having multiple ShardedCounterFields on the same model.
        self.shard_count = shard_count
        if shard_count > MAX_ENTITIES_PER_GET:
            raise ImproperlyConfigured(
                "ShardedCounterField.shard_count cannot be more than the Datastore is capable of "
                "fetching in a single Get operation (%d)" % MAX_ENTITIES_PER_GET
            )
        kwargs.setdefault("related_name", "+")
        super(ShardedCounterField, self).__init__(CounterShard, *args, **kwargs)

    def contribute_to_class(self, cls, name):
        super(ShardedCounterField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, ReverseRelatedShardsDescriptor(self))
