# Migrations

    **Djangae Migration support is highly-experimental, please test your migrations thoroughly before running on production data**

Migrations are generally required on SQL databases to change table structures to reflect changes in your models. Although using a
non-relational datastore removes the need for schema migrations, data migrations are still sometimes necessary. It's common to
take care of these data migrations "on-the-fly" by writing code to manipulate the data during the normal usage of the app (for example in an overridden `save()` method) however there are times when it would be useful to run a data migration on all the entities in a table.

Djangae has support for running these kinds of migrations by using the normal Django migrations infrastructure. It provides a series of
custom migration operations which will run tasks on the App Engine task queue to update the required entities.

One thing to consider is that this migrations only work if the migration file is deployed. The process of running a Djangae migration would be:

1. Write a migration file which uses Djangae migration operations
2. Deploy the code to App Engine and make that version live
3. Run the migration using the remote sandbox (e.g. `manage.py --sandbox=remote migrate`)

    **Note: It is a current limitation that you cannot run a migration while it's on a non-default version, this will hopefully be fixed by allowing a version to be specified to the remote sandbox**

There are a few important things to understand about Djangae's migrations:

1. Migrations run on the entity-level, not the Django model instance level. Custom `save()` code will not be called - this is the equivalent of running SQL queries directly on a relational database
2. Djangae data migrations are not transactional as a whole, if something goes wrong the migration might only run on some entities
3. An operation may run more than once per entity. If there is an error while a task shard is processing, then that shard will retry, and will run the operation again on all of the entities in that shard. Be sure that running the same migration operation twice on the same entity will not break anything.
4. If an error occurs, you'll need to deploy code to fix it, otherwise the migration will be "stuck". If one entity causes an error, the shard will restart from the beginning, if that same entity repeatedly causes an error then the data migration will never complete. You should watch the error logs while a migration is running and if an error repeatedly happens you will need to fix it locally then redeploy.

   **Note: Before writing a Djangae migration, consider if it's even necessary. For example, if you're just adding a new field but never querying on it directly, then just add a default to the model field and this will be populated as your instances are saved during the normal running of the app. If you need to query on the new field then you may need to run a Djangae migration so that field is indexed on all entities**

## Writing Data Migrations

It is important that you do not mix Django migration operations and Djangae migration operations in the same migration file. The reason for this is that if a migration is interrupted and subsequently repeated, any complete Djangae migrations will be skipped but Django ones will retry.

It's important to note that any Django migration operations (e.g. AddField, AddModel) that happen on the datastore will be no-ops, but you still need to include any Django-generated migrations so that the Djangae migrations have access to the latest model state.

It's also important to understand that for various reasons an entity may be processed twice or more while running a migration so your migration operations should be able to handle this.

## Migration Operations

This section summarizes the different migration operations available in Djangae and the steps that must be taken for them to work properly.

### Add Field

**Steps**

1. Run the normal `django...AddField` operation
2. Deploy new model code.
3. Run the `djangae...AddFieldData` operation to populate the new field (optional).
4. Deploy code which queries on the new field (optional).


**Explanation**

If you don't need to query on the new field, then all you need to do is add the field to your model (step 1) and ensure that the field either has a `default` or has `null=True`.
As instances are loaded from the DB and re-saved as part of the general running of your application, they will be re-saved with the default value.
You can skip steps 3 and 4.

If however, you need to be able to filter on the new field in your queries, then you will need to run step 3 in order to populate the value into the DB (and thus into the Datastore indexes).
It is recommended that you deploy the new model code _before_ runing the `AddFieldData` operation.
This is because if you populate the existing objects in the Datastore with the default field value _before_ adding the field to the model, then if your application creates any new model instances after the `AddFieldData` process is started then you may end up with objects which do not have the default value set.
But if, as recommended, you add the field to your model first, then any new objects created will get the default value (assuming you've set a `default` on the field), and the existing objects will be populated by the `AddFieldData` process, meaning that no objects are missed.


### Remove Field

**Steps**

1. Run the normal `django...RemoveField` operation.
2. Deploy new model code.
3. Run a `djangae...RemoveFieldData` operation (optional).


**Explanation**

If you remove a field from a model and you do not run the `RemoveFieldData` process, then any existing objects will simply keep the old field value in their underlying Entity in the Datastore.
The only problem with this is that it takes up storage space in your Datastore which costs you money.
But note that running the `RemoveFieldData` process will cause Datastore writes and use instance hours, which will also cost you money.
Whether you want to run the `RemoveFieldData` task or not depends on how much data there is and how long you expect your application to live for, weighted with the various costs involved in storing or removing it.


### Rename Field

**Steps**

1. Run the normal `django...AddField(new_field)` operation.
2. Create `save` method to ensure that any value which is saved to the old field is also saved to the new field.
3. Deploy new code.
4. `djangae...CopyFieldData(old_field, new_Field)`.
5. `django...RemoveField(old_field)`.
6. `djangae...RemoveFieldData(old_field)` (optional).


**Explanation**

Renaming a field requires adding a new field, copying the data from the old field, and then removing the old field, but in doing so ensuring that any objects which are created or edited during that process have their (latest) values for the old field copied across.


### Delete Model Data

The `DeleteModelData` operation deletes all the data related to a particular model (essentially `DROP TABLE X`)
there is no special process required here, just use this operation carefully!

### Copy Data from One Model to Another

The `CopyModelData` operation copies all the row data for a model into another. Both model classes must exist in your project for the operation to work.

### Copy Data for a Model into a Different Namespace

The datastore has muliple namespaces (similar to separate databases), the `CopyModelDataToNamespace` operation copies
the data for a model into a specified namespace. You can then access this data by adding another connection
to your `DATABASES` setting.

### Custom Processing Per Entity

The `MapFunctionOnEntities` operation allows you to run a custom function on all the entities of a model class. Note that the function
must be able to be pickled and that the function is provided an entity, not a Django model instance.

# Settings

## `DJANGAE_MIGRATION_DEFAULT_SHARD_COUNT`

Sets the default number of shards that migration use. Higher values will perform migrations more quickly, but this will spin update
more instances and so cost more.

## `DJANGAE_MIGRATION_DEFAULT_ENTITIES_PER_TASK`

The number of entities a migration task will process before stopping and continuing with a fresh task. Each shard runs a series of tasks
serially to avoid exceeding App Engine task deadlines. If you increase this value you increase the risk of hitting a deadline error.

# Potential Future Improvements / Additions

* Remove model
* Move/rename model.
* Move a model to a different namespace.
* Custom data fiddling.
* Do the arguments to the various operations make sense, and are they consistent?  E.g. for CopyFieldData, should it take a field, rather than just the column name?
* Should the `to_model_app_label` kwarg for CopyModelDataToNamespace be named better?  Should it just be `to_app_label`?

# Migration Operation Ambiguity

The datastore migration tasks work by creating markers in the datastore to represent each individual operation. These markers keep track of the progress of the operation (i.e. whether or not it's finished).

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
the third migration will fail as the operation would appear to have been completed. You can avoid this situation by providing a `uid` argument
to the operation:

```
class Migration(migrations.Migration):
    operations = [
        AddFieldData("mymodel", "myfield", ..., uid="first_migration")
    ]
```

The `uid` will be added to the task marker and so there won't be a clash in future. It's good practice to specify the uid to be safe, perhaps using the date the migration file was created.
