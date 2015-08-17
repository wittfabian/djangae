# Unique constraint tool

## Djangae unique constraint support

The App Engine Datastore doesn't support unique constraints, with the exception of named keys.
Djangae exploits this uniqueness of the key to allow it to provide unique constraints and
unique-together constraints on other fields, as you would get with a SQL database.

It does this by storing a separate table of **Marker** entities, with one marker per unique
constraint per model instance.  The key of the marker is an encoded combination of the model/table
and the name(s) and value(s) of the unique field(s) in the constraint.  Each marker entity also
stores an **instance** attribute pointing back to the instance that actually uses the unique value.
That attribute is updated after the marker is created (because the marker is created first for new
instances, before we even know their keys) so it might be invalid in some situations.


## The Uniquetool

The tool plugs into Django Admin and allows examining or repairng of the Markers for a given model.
There are 3 actions you can perform for any model defining a unique constraint.  To perform an
action, create a "Unique action" object in the Django admin, setting the "Model" to the model which
you want to check and the "Action type" to the action which you want to perform.  Creation of the
object will trigger a task in the background, the status of which will be shown on the object in
the admin site.

### Check

Examines all instances and verifies that all of it's unique values are properly backed
by Marker entities in the datastore.

### Repair

Ensures that all instances with unique values own their respective markers. Missing markers are
recreated and ones missing the instance attr are pointed at the right instance. In case a marker
already exists, but points to a different instance it is logged as it's an actual integrity
problem and has to be resolved manually (change one of your instance's value so it's unique).

This action is useful when migrating an existing model to start using the unique constraint
support.

### Clean

TODO: Docs needed.


## UniquenessMixin

If you want to mark a `ListField` or a `SetField` as unique or use `unique_together`
Meta option with any of these fields, it is also **necessary** to use `UniquenessMixin`.:

```
from django.db import models
from djangae.fields import SetField, ListField
from djangae.db.constraints import UniquenessMixin


class Princess(UniquenessMixin, models.Model):
    name = models.CharField(max_length=255)
    potential_princes = SetField(models.CharField(max_length=255), unique=True)
    ancestors = ListField(models.CharField(max_length=255), unique=True)
```
