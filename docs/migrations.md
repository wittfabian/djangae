# Migrations

Imagine banter here about:

* How the concept(s) of migrations are generally different, i.e.:
  - Migrations on the Datastore do not move data from state A to state B in a transaction, they move it gradually while the application is still running.
  - This is great because you don't have to take your site down.
  - This is a pain because you have to think about your migrations carefully.
* How migrations on the Datastore are often not necessary (e.g. for adding a new model, or adding a new field), unless you need to:
  - Get rid of the old data.
  - Query on a newly-added field.
  - Move data, e.g. renaming a field.
* How the Django migration operations (AddModel, AddField, etc) will deliberately be no-ops, becase we can't decide for you whether you want to actually do a data migration.
* Ergo... if you want to do a data migration, Djangae provides a bunch of custom migration operations which you can put into custom migrations to do what you want.
* You will still need to include Django's auto-generated migration files in your 'migrations' folder(s), because without them the Djangae migrations will not be given the correct state of the models.
* You MUST NOT put djangae operations in the same migration file as Django operations.
* Note that if you run an operation and then change the parameters of an operation, it will be treated as a new operation and if the migration in which it resides is run again, the operation will be run (again).
* The entity-based operations work directly with the underlying Datastore entities, and therefore do not update any `auto_now` or `auto_now_add` values.
* When using the `CopyModelData` operation, be aware that it is simply copying the data with no regard for any differences there may be between the two models.

## Reference Guide For How To Do Each Kind of Migration


### Add Field

**Steps**

1. `django...AddField`.
2. Deploy new model code.
3. `djangae...AddFieldData` (optional).
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

1. `django...RemoveField`.
2. Deploy new model code.
3. `djangae...RemoveFieldData` (optional).


**Explanation**

If you remove a field from a model and you do not run the `RemoveFieldData` process, then any existing objects will simply keep the old field value in their underlying Entity in the Datastore.
The only problem with this is that it takes up storage space in your Datastore which costs you money.
But note that running the `RemoveFieldData` process will cause Datastore writes and use instance hours, which will also cost you money.
Whether you want to run the `RemoveFieldData` task or not depends on how much data there is and how long you expect your application to live for, weighted with the various costs involved in storing or removing it.


### Rename Field

**Steps**

1. `django...AddField(new_field)`.
2. Create `save` method to ensure that any value which is saved to the old field is also saved to the new field.
3. Deploy new code.
4. `djangae...CopyFieldData(old_field, new_Field)`.
5. `django...RemoveField(old_field)`.
6. `djangae...RemoveFieldData(old_field)` (optional).


** Explanation**

Renaming a field requires adding a new field, copying the data from the old field, and then removing the old field, but in doing so ensuring that any objects which are created or edited during that process have their (latest) values for the old field copied across.


TODO:
* Remove model
* Move/rename model.
* Move a model to a different namespace.
* Custom data fiddling.


QUESTIONS / DESIGN DECISIONS:

* Do the arguments to the various operations make sense, and are they consistent?  E.g. for CopyFieldData, should it take a field, rather than just the column name?
* Is `to_model_app_label` a crap kwarg name for CopyModelDataToNamespace?  Should it just be `to_app_label`.

