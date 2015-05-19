import random

from django.db import models

from djangae.fields.related import (
    RelatedSetField,
    RelatedSetManagerBase,
    ReverseRelatedSetObjectsDescriptor,
)
from djangae.models import CounterShard
from djangae.db import transaction


MAX_ENTITY_GROUPS_PER_TRANSACTION = 25


class RelatedShardManager(RelatedSetManagerBase, CounterShard._default_manager.__class__):
    """ This is what is given to you when you access the field attribute on an instance.  It's a
        model manager with the usual queryset methods (the same as for RelatedSetField) but with
        the additional increment()/decrement()/reset() methods for the counting.
    """

    def increment(self, step=1):
        self._update_or_create_shard(step)

    def decrement(self, step=1):
        step = -abs(step) # handle people passing in 1 or -1 or +/- whatever
        self._update_or_create_shard(step)

    def value(self):
        """ Calcuate the aggregated sum of all the shard values. """
        shards = self.all().values_list('count', flat=True)
        return sum(shards)

    def reset(self, save=True):
        """ Delete all of the shards for this counter (setting it to 0). """
        def _reset():
            self.all().delete()
            setattr(self.instance, self.field.attname, set())
            if save:
                self.instance.save()

        # If we have few enough shards then we can do this transactionally.
        # There is only point in doing this if we're saving the model instance.
        if save and len(self) < MAX_ENTITY_GROUPS_PER_TRANSACTION:
            _reset = transaction.atomic(xg=True)(_reset)

        _reset()

    def clear(self):
        # Override the default `clear` method of the parent class, as that only clears the list of
        # PKs but doesn't delete the related objects.  We want to delete the objects (shards) as well.
        self.reset()

    def populate(self, save=True):
        """ Create all the CounterShard objects which will be used by this field. Useful to prevent
            additional saves being caused when you call increment() or decrement() due to having to
            update the list of shard PKs on the instance.
        """
        num_to_create = self.field.shard_count - len(self)
        if not num_to_create:
            return

        def _populate():
            # TODO: use a bulk-create thing here
            for x in xrange(num_to_create):
                self.add(self._create_shard(count=0))
            if save:
                self.instance.save()

        # If we have few enough shards then we can do this transactionally
        # There is only point in doing this if we're saving the model instance.
        if save and num_to_create < MAX_ENTITY_GROUPS_PER_TRANSACTION:
            _populate = transaction.atomic(xg=save)(_populate)

        _populate()

    def _update_or_create_shard(self, step):
        shard_index = random.randint(0, self.field.shard_count - 1)
        # Converting the set to a list introduces some randomness in the ordering, but that's fine
        shard_pks = list(self.field.value_from_object(self.instance)) # needs to be indexable
        try:
            shard_pk = shard_pks[shard_index]
        except IndexError:
            # We don't have this many shards yet, so create a new one
            with transaction.atomic(xg=True):
                new_shard = self._create_shard(count=step)
                self.add(new_shard)
                self.instance.save()
        else:
            with transaction.atomic():
                shard = CounterShard.objects.get(pk=shard_pk)
                shard.count += step
                shard.save()

    def _create_shard(self, count):
        return CounterShard.objects.create(
            count=count, label="%s.%s" % (self.instance._meta.db_table, self.field.name)
        )


class ReverseRelatedShardsDescriptor(ReverseRelatedSetObjectsDescriptor):
    """ Subclass of the RelatedSetField's ReverseRelatedSetObjectsDescriptor which overrides the
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

    def __init__(self, shard_count=30, related_name="+", *args, **kwargs):
        # Note that by removing the related_name by default we avoid reverse name clashes caused by
        # having multiple ShardedCounterFields on the same model.
        self.shard_count = shard_count
        super(ShardedCounterField, self).__init__(CounterShard, *args, **kwargs)

    def contribute_to_class(self, cls, name):
        super(ShardedCounterField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, ReverseRelatedShardsDescriptor(self))
