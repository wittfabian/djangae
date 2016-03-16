# Djangae Model Fields

## ListField / SetField

These allows you to store a list/set of values (strings, floats, integers dates) in a single field.
This is often useful when structuring data for a non-relational database. [See example usage](fields.md#example-usages).

```ListField(item_field_type, **kwargs)```


* `item_field_type`: An instance of a Django model field which defines the data type and validation for each item in the list.
* `ordering`: A callable which allows the items in the list to be automatically sorted.


```SetField(item_field_type, **kwargs)```

* `item_field_type`: An instance of a Django model field which defines the data type and validation for each item in the list.


Both fields also accept the following standard Django model field kwargs:

* `default`: works as normal.
* `blank`: works as normal.
* `null`: this cannot be set to `True`.  The App Engine Datastore does not allow us to differentiate between `[]` and `None`, so we stick with the former.
* `validators`: works as normal, but note that it's important where you pass this argument; if you pass it to the `ListField` or `SetField` then the validators operate on the list/set as a whole, but if you pass it to the nested model field then the validators operate on each individual value.
* `choices`: this works as normal, but should be passed to the nested model field, not to the `ListField`/`SetField` itself.  In a form this results in a multiple select field.
* `unique`: works as normal, but note that this relates to the uniqueness across different instances, not uniqueness within the list of values.  If you just want to remove duplicates from the list of values in the field then use `SetField`; setting `unique=True` will check that no 2 objects contain *any* of the same values for this field.
* `editable`: works as normal.
* `help_text`: works as normal.
* `verbose_name`: works as normal.

Djangae makes some effort to provide a sensible form field for `ListField`/`SetField`, but you may find that in some cases you need to customise or change this behaviour to suit your usage.


## RelatedSetField

This is essentially a substitue for `ManyToManyField`, but which works on the non-relational App Engine Datastore.
It works by storing a list of primary keys of the related objects.  Think of it as a `SetField` with a layer of manager/query magic on top which allow you to create it much like a `ManyToManyField`. [See example usage](fields.md#example-usages).

```RelatedSetField(related_model, **kwargs)```

* `model`: the model of the related items.
* `limit_choices_to`: a dictionary of query kwargs for limiting the possible related items.
* `related_name` - the name of the reverse lookup attribute which is added to the model class of the related items.


The `RelatedSetField` also accepts most of the same kwargs as `SetField`.


## RelatedListField

RelatedListField shares the same behavior as RelatedSetField but has the qualities of a list; it maintains the ordering of related objects and allows duplicates.

```RelatedListField(related_model, **kwargs)```

* `model`: the model of the related items.
* `limit_choices_to`: a dictionary of query kwargs for limiting the possible related items.
* `related_name` - the name of the reverse lookup attribute which is added to the model class of the related items.


## ShardedCounterField

This field allows you to store a counter which can be incremented/decremented at an extremely high rate without causing database contention.  Given that the Datastore is not performant at doing `count()` queries, this is an excellent way of counting large numbers on the Datastore. [See example usage](fields.md#example-usages).

It works by creating a set of `CounterShard` objects, each of which stores a count, and each time you call `.increment()` or `.decrement()` on the field it randomly picks one of its `CounterShard` objects to increment or decrement.  When you call `.value()` on the field it sums the counts of all the shards to give you the total.  The more shards you specify the higher the rate at which it can handle `.increment()`/`.decrement()` calls.

```ShardedCounterField(shard_count=24, related_name="+", **kwargs)```

* `shard_count`: the number of `CounterShard` objects to use.  The default number is deliberately set to allow all of the shards to be created (and the object to which they belong updated) in a single transaction.  See the `.populate()` method below.
* `related_name`: the name of the reverse relation lookup which is added to the `CounterShard` model.  This is deliberately set to `"+"` to avoid the reverse lookup being set, as in most cases you will never need it and setting it gives you the problem of avoiding clashes when you have multiple ShardedCounterFields on the same model.

When you access the attribute of your sharded counter field on your model, you get a `RelatedShardManager` object, which has the following API:

* `.value()`: Gives you the value of counter.  This is immediately consistent (i.e. is not affected by the Datastore's eventual consistency behaviour).
* `.increment(step=1)`: Transactionally increment the counter by the given step.
    - If you have not yet called `.populate()` then this might also cause your model object to be re-saved, depending on whether or not it needs to create a new shard.
* `.decrement(step=1)`: Transactionally decrement the counter by the given step.
    - If you have not yet called `.populate()` then this might also cause your model object to be re-saved, depending on whether or not it needs to create a new shard.
* `.populate()`: Creates all the shards that the counter will need.
     - This is useful if you want to ensure that additional saves to your model object are avoided when calling `.increment()` or `.decrement()`, as these saves may cause issues if you're doing things inside a transaction or at such a rate that they cause DB contention on your model object.
     - Note that this causes your model instance to be re-saved.
* `.reset()`: Resets the counter to 0.
    - This is done by changing the value of the shards, not by deleting them.  So you can continue to use your counter afterwards without having to call `populate()` again first.


### Additional notes:

* Counts can be negative.
* `ShardedCounterField` is a subclass of `RelatedSetField`, so in addition to the above API you also have the manager methods from `RelatedSetField` such as `.filter()`, etc.  These probably aren't very useful though!
* For convenience (or more likely, disaster recovery), each `CounterShard` has a `label` field which contains a reference to the model and field for which it is used in the format `"db_table.field_name"`.  So should you ever need to go and actually look at/alter the `CounterShard` objects, you can see which ones are used for what.


## GenericRelationField

This is a replacement for Django's `GenericForeignKey` field, which doesn't use Django's contenttypes, and consequently it allows querying by the related object even on the non-relational Datastore.  (Django's `GenericForeignKey` would cause a JOIN if you tried to do do that.)

This field requires no special kwargs, and should accept all standard Django field kwargs as normal.

## CharField

This is a replacement for Django's `CharField` field. It uses the `MaxBytesValidator` validator that makes sure the value does not exceed the hard datastore limit of 1500 bytes (see `google.appengine.api.datastore_types _MAX_STRING_LENGTH`). Use this field whenever you're planning to store large char values in the datastore, else your data may get silently trimmed.

## JSONField

This field is not specific to the App Engine Datastore (or any non-relational database), but is included in Djangae for convenience, especially as in a non-relational database it's often useful to be able to store structured data in a single table rather than in a complex structure of related tables.

```JSONField(use_ordered_dict=False, **kwargs)```

* `use_ordered_dict`: (default: False) Use `collections.OrderedDict` rather than built-in `dict`.


## TrueOrNullField

This field is not specific to the App Engine Datastore (or any non-relational database), but is included in Djangae for convenience.

Its primary use case is for when you want a boolean field which can only be set to true for *one* object.  This is done by making use of the fact that Django (and most databases) ignore `None` values in unique constraints, so by having a field which can only store values of `True` or `None` and by setting the field to unique, you get a field which can only be `True` on one object.


## Example Usages


```
from django.db import models
from djangae import fields

class KittenSanctuary(models.Model):

    is_best = fields.TrueOrNullField(unique=True)
    kittens = fields.RelatedSetField('Kitten')
    kitten_rota = fields.RelatedListField('Kitten')
    inspection_dates = fields.SetField(models.DateField())
    historic_weekly_kitten_count = fields.ListField(models.PositiveIntegerField())
    number_of_meows = fields.ShardedCounterField()
    current_staff_rota = fields.JSONField()


def new_kitten_arrival(sanctuary, kitten):
    sanctuary.kittens.add(kitten)
    sanctuary.save()

def log_inspection(sanctuary):
    sanctuary.inspection_dates.add(timezone.now())
    sanctuary.save()

def log_meow(sanctuary):
    sanctuary.number_of_meows.increment()
    # Note that we don't need to save the object
    print sanctuary.number_of_meows.value()
```
