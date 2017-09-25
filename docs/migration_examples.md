# Migration Examples

As a supplement to the [migrations documentation](migrations.md), this page gives some code examples and various common scenarios, showing how Djangae migrations may be used in practice.

## Example Migration File

This migration file would live alongside your auto-generated Django migration files inside the `migrations` folder in your Django app.  You should name the file just like you would with a normal Django migration file, e.g. `0004_add_favourite_colour_field_data.py`.

```python
from djangae.db.migrations.operations import AddFieldData
from djangae.fields import CharField
from django.db import migrations


class Migration(migrations.Migration):
    """ Populates the Person model with the default value for the new `favourite_colour` field. """
    
    operations = [
        AddFieldData(
            "myapp.Person",
            "favourite_colour",
            CharField(default="blue")
        )
    ]
```

## Example Migration Scenarios

One of the great advantages of a schemaless database is that you can incrementally modify the data structure, even on extremely large tables, and even while the application is in use.  However, this departure from the "Turn it off, run a migration, turn it back on again" approach means that planning data migrations often requires a bit more thought.

Below are some examples of how one might approach different migration scenarios.

### Add Field

**Steps**

1. Run the migraton containing the normal `django...AddField` operation
2. Deploy new model code.
3. Run a migration containing the `djangae...AddFieldData` operation to populate the new field (optional).
4. Deploy code which queries on the new field (optional).


**Explanation**

If you don't need to query on the default value of the new field, then all you need to do is add the field to your model (step 1) and ensure that the field either has a `default`, has `null=True`, or is a `CharField` or `TextField` (which effectively have a default of `""`).
As instances are loaded from the DB and re-saved as part of the general running of your application, they will be re-saved with the default value.
You can skip steps 3 and 4.

If however, you need to be able to filter on the default value of the new field in your queries, then you will need to run step 3 in order to populate the value into the DB (and thus into the Datastore indexes).
It is recommended that you deploy the new model code _before_ runing the `AddFieldData` operation.
This is because if you populate the existing objects in the Datastore with the default field value _before_ adding the field to the model, then if your application creates any new model instances while the `AddFieldData` process is running then they may not get caught by that process and you may therefore end up with objects which do not have the default value set.
But if, as recommended, you add the field to your model first, then any new objects created will get the default value, and the existing objects will be populated by the `AddFieldData` process, meaning that no objects are missed.


### Remove Field

**Steps**

1. Run the migration containing the normal `django...RemoveField` operation.
2. Deploy new model code.
3. Run a migration containing a `djangae...RemoveFieldData` operation (optional).


**Explanation**

If you remove a field from a model and you do not run the `RemoveFieldData` operation, then any existing objects will simply keep the old field value in their underlying entities in the Datastore.
The only problem with this is that it takes up storage space in your Datastore which costs you money.
But note that running the `RemoveFieldData` process will cause Datastore writes and use instance hours, which will also cost you money.
Whether you want to run the `RemoveFieldData` task or not depends on how much data there is and how long you expect your application to live for, weighted with the various costs involved in storing or removing it.


### Rename Field

**Steps**

1. Run the migration containing the normal `django...AddField(new_field)` operation.
2. Create `save` method to ensure that any value which is saved to the old field is also saved to the new field.
3. Deploy new code.
4. Run migrations containing the following operations (note that these are a mix of _django_ and _djangae_ operations, so each must be in a separate migration file):
    * `djangae...CopyFieldData(old_field, new_Field)`.
    * `django...RemoveField(old_field)`.
    * `djangae...RemoveFieldData(old_field)` (optional).


**Explanation**

Renaming a field requires adding a new field, copying the data from the old field, and then removing the old field, but in doing so ensuring that any objects which are created or edited during that process have their (latest) values for the old field copied across.


### Delete Model Data

**Steps**

1. Run the migration containing the normal `django...AddField(new_field)` operation.
2. Deploy new code.
3. Run a migration containing a `djangae... DeleteModelData` operation (optional).

**Explanation**

The `DeleteModelData` operation deletes all the data related to a particular model (essentially `DROP TABLE X`).  There is no special process required here, just use this operation carefully!

### Copy Data from One Model to Another

The `CopyModelData` operation copies all the row data for a model into another. Both model classes must exist in your project for the operation to work.  The exact steps that you use here will probably depend on what you're doing with those models.

### Copy Data for a Model into a Different Namespace

The `CopyModelDataToNamespace` operation will effectively copy an entire table (kind) from one Datastore namespace to another.  The exact steps that you use here will probably depend on what you're doing with those 2 namespaces.


### Custom Changes

For any other custom data manipulations, you can use the  `MapFunctionOnEntities` operation to call a custom function on each entities of a model class.