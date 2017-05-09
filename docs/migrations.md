# Migrations

    **Djangae Migration support is new, and therefore is classed as "experimental". Please test your migrations thoroughly before running on production data**

Migrations are generally required on SQL databases to change table structures to reflect changes in your models. Although using a
schemaless database removes the need for schema migrations, _data_ migrations are still sometimes necessary. It's common to
take care of these data migrations "on-the-fly" by writing code to manipulate the data during the normal running of the application (for example in an overridden `save()` method) however there are times when it is useful to run a data migration on all the entities in a table.

Djangae has support for running these kinds of migrations by using Django's migrations infrastructure. It provides a series of
custom migration operations which will run tasks on the App Engine task queue to update the required entities.

# General Concepts

There are various key differences between using "normal" Django migrations and using migrations with the Datastore.

### Do you need a migration? 
The first difference is that you don't always need a migration at all.  The Datastore is schemaless, and therefore you can, for example, add a new Django model, and just save an instance of that model; you don't need to tell the database to create a "table" for it first.  Similarly, you can add a new field to a model and simply deploy the new code without adding a new "column" to the "table"; when Django encounters an object where the value is missing it simply uses the field's default value, and will add the value to the DB on save.

The times when you _do_ need to use a migration are usually when either:

1. You need to query on the new data.  (You can't query on values that don't exist. Even if the query is for None/NULL, it will _not_ return rows where the value is not actually set to `None`.)
2. You actually want to delete the old data.  On the Datastore one cannot simply `DROP` a table or column, so the only way to delete data is delete (values from) entities individually.

### Django's operations are ignored

The next difference is that the Djangae Datastore backend will ignore Django's standard migration operations.  This is largely because, as just noted, the decision of what to do when you add/remove a field/model depends on your specific case.  So rather than trying to guess what you want to do, Djangae ignores Django's operations and provides a separate set of Datastore-specific operations to allow you to specify what you want to do, which might be nothing.

Note that Django's migration operations are not _just_ about the database changes; they also provide the model state history.  So you should not delete Django's auto-generated migration files. You should just add your own additional files with the Datastore operations that you wish to perform.

Due to the way that migrations are run on the Datastore, you cannot mix Django operations with Djangae operations in the same migration file.

You should not try to use Django's `RunPython` operation to make changes on the Datastore, as the supplied function will be executed on your local machine, rather than in a task queue on the live App Engine site.

### Other differences

* Migrations run on the entity level, not the Django model instance level. Custom `save()` code will not be called. They are the equivalent of running SQL queries directly on a relational database.
* Djangae data migrations are not transactional as a whole, if something goes wrong the migration might only run on some entities.
* An operation may run more than once per entity. If there is an error while a task shard is processing (and you have not set `skip_errors` to `True`), then that shard will retry, and will run the operation again on all of the entities in that shard. Be sure that running the same migration operation twice on the same entity will not break anything.
* If an error occurs, you'll need to deploy code to fix it, otherwise the migration will be "stuck". If one entity causes an error (and you have not set `skip_entities` to `True`), the shard will restart from the beginning, if that same entity repeatedly causes an error then the data migration will never complete. You should watch the error logs while a migration is running and if an error repeatedly happens you will need to fix it locally then redeploy.



## Writing & Running Migrations

The process of writing and running a Djangae migration is:

1. Run Django's `makemigrations` command as normal to create the auto-generated migration file(s).  These ensure that the model state is handled correctly, even though the actual database operations are ignored.
1. Write a separate migration file which uses Djangae migration operations to perform the data changes you want.
1. Deploy the code to App Engine and make that version the default.
3. Run the migration using the remote sandbox (e.g. `manage.py --sandbox=remote migrate`).

The command will queue tasks on the live site's, and will then continue to check to see when the operations are complete, giving you a running status update in the terminal.  You can kill and restart the `migrate` command without affecting the migration, but the command must be running in order for it to move from one operation to the next. Similarly, running the `migrate` command from another machine (even at the same time) will not have a negative effect, as the triggering of the operation tasks is transactional.

### Limitations for running migrations

* Migrations only work if the migration file is deployed.  This is because although migrations are _triggered_ from the terminal, they _run_ on the actual App Engine application using the deployed code.
* Currently, you cannot run a migration while it's on a non-default version, this will hopefully be fixed by allowing a version to be specified to the remote sandbox.


## Migration Operations

This section summarizes the different migration operations available in Djangae.  For a more in-depth look at using these, see the [Migration examples](migration_examples.md).


## Operation Options

The following arguments are available to all Djangae operations. All are optional.

#### `uid`

This is used to uniquely identify multiple operations which have identical parameters.  See [Migration Operation Ambiguity](#migration-operation-ambiguity).

Default: `""`

#### `shard_count`

Specifies the number of simultaneous shards for processing the entities.  More shards will process the data faster, but will spin up
more instances of your application and so might cost more.

Default: see [Settings](#settings)

#### `entities_per_task`

Specifies the number of entities to process in a single task before stopping and continuing in a fresh task.
Each shard runs a chains of tasks serially to avoid exceeding [App Engine task deadlines](https://cloud.google.com/appengine/docs/standard/python/taskqueue/push/). If you increase this value you increase the risk of hitting a deadline error.

Default: see [Settings](#settings)


#### `queue`

Specifies the name of the task queue which should be used for processing the entities.

Default: see [Settings](#settings)

#### `skip_errors`

Specifies whether the operation should skip over entities which cause an error and continue with processing.  If this is set to `True`, then when an error is encountered processing an entity, it is logged, but processing continues and the operation will be marked as completed despite these errors.  If set to `False` then any error will cause the task to retry, meaning that (assuming you haven't set a `max_retries` limit on the queue) the migration will remain in progress until you fix the error.

Bear in mind that if you set this to `True` then even transient errors, such as transaction collisions will be caught by this, meaning that you might skip entities unnecessarily.  `DeadlineExceededError` is the only error which is not skipped.

Default: `False`



## `AddFieldData`

Adds the `default` value for a field to all entities in the model.  Respects custom `db_column` on the field, if there is one.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.
* `name` - name of the field, e.g. `is_blue`.
* `field` - instance of the field, e.g. `BooleanField(default=True)`.

## `RemoveFieldData`

Removes data for the given field from the given model.  Respects custom `db_column` on the field, if there is one.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.
* `name` - name of the field, e.g. `is_blue`.
* `field` - instance of the field, e.g. `BooleanField(default=True)`.

## `CopyFieldData`

Copies data from one field on a model to another.  Takes the *db colum* names rather than the field names.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.
* `from_column_name` - column name to copy data from.
* `to_column_name` - column name to copy data to.

## `DeleteModelData`

Deletes all data for the given model from the DB.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.

## `CopyModelData`

Copies all data from one model into the table (kind) of another model.  This copies the entire entities as they are, regardless of the fields on the model class.  The primary keys of the new entities are the same as the original entities.  The model that you are copying data _to_ does not necessarily need to be in the same Django app as the model that you're copying _from_.  But the migration file must live in the app which you are copying _from_.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.
* `to_app_label` - label of Django app of target model.
* `to_model_name` - case sensitive name of target model.
* `overwrite_existing` - boolean, default: `False`.

## `CopyModelDataToNamespace`

The Datastore has muliple namespaces, which with Djangae are exposed to Django as separate databases (see [Database Backend](db_backend.md#multiple-namespaces)).

This operation copies all data from a model in the source database into a different Datastore namespace.  By default it copies the data into a model of the same kind in the same app.  In other words, the "table" (Datastore Kind) stays the same.  But you can optionally specify a different `app_label` and `to_model_name` to copy the data into.  The primary keys of the new entities are the same as the original entities.  The source database is whichever database the migration is being run on (which is the default database, unless you've passed the `--database` option to the `migrate` command).

**Parameters:**

* `model_name`- case sensitive model name, e.g. `Person`.
* `to_namespace` - string name of Datastore namespace to copy data to.
* `to_app_label` - optional label of Django app of target model (if different).
* `to_model_name` - optional case sensitive target model name (if different).
* `overwrite_existing` - boolean, default: `False`.


## `MapFunctionOnEntities`

Runs a custom function on all entities from the given model.

**Parameters:**

* `model_name` - case sensitive model name, e.g. `Person`.
* `function` - pickle-able function to be called on each Datastore entity.

Note that the function is called with each Datastore _entity_, not with each Django model instance.  Support for calling a function on each Django model instance is a planned future feature.


# Settings

The following settings can be added to your Django settings module to affect the behaviour of Djangae migrations.

## `DJANGAE_MIGRATION_DEFAULT_SHARD_COUNT`

Sets the default `shard_count` value for all operations that do not specify otherwise.

Default: `32`

## `DJANGAE_MIGRATION_DEFAULT_ENTITIES_PER_TASK`

Sets the default `entities_per_task` value for all operations that do not specify otherwise.

Default: `100`


## `DJANGAE_MIGRATION_DEFAULT_QUEUE`

Sets the default `queue` value for all operations that do not specify otherwise.

Default: `None` (which will result in the `"default"` queue being used)

# Migration Operation Ambiguity

The way that Django tracks migrations is on a per-migration basis, rather than a per-operation basis.  And it assumes that each migration will either be "done" or "not done"; there's no "in progress".  Given that operations on the Datastore cannot be treated in this way, the Datastore migrations work by creating markers in the Datastore to represent each individual operation. These markers keep track of the progress of the operation (i.e. whether or not it's been started/finished).

Unfortunately there is no concrete way to uniquely identify an operation, take for example the following migrations:

```
# First migration

class Migration(migrations.Migration):
    operations = [
        AddFieldData("mymodel", "myfield", ...)
    ]


# Second migration

class Migration(migrations.Migration):
    operations = [
        RemoveField("mymodel", "myfield", ...)
    ]

# Third migration

class Migration(migrations.Migration):
    operations = [
        AddFieldData("mymodel", "myfield", ...)
    ]
```

Here, the first and third migrations have operations that will clash as they are the same operation, with the same arguments. In this situation
the third migration will have no effect, as the operation would appear to have been completed. You can avoid this situation by providing a `uid` argument
to the operation:

```
class Migration(migrations.Migration):
    operations = [
        AddFieldData("mymodel", "myfield", ..., uid="first_migration")
    ]
```

The `uid` will be added to the task marker and so there won't be a clash in future. It's good practice to specify the uid to be safe, perhaps using the date the migration file was created.
