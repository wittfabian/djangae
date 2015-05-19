# Unique constraint tool

## Djangae unique constraint support

The datastore doesn't support unique constraints with the exception of named keys. Djangae
exploits this storing a **Marker** entity whose key encoded the used unique value.
The marker entities also store an **instance** attribute pointing back to the instance that
actually uses the unique value. That attribute is updated after the marker is created
(because the marker is created first for new instances, before we even know their keys)
so it might be invalid in some situations.


## The Uniquetool

The tool plugs into Django Admin and allows examining or repairng the Markers for a given model.
You can start the following 3 actions for any Model defining a unique constraint:

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

