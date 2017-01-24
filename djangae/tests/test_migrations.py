# STANDARD LIB
from unittest import skipIf

# THIRD PARTY
from django.apps.registry import apps  # Apps
from django.conf import settings
from django.db import connection, models
from django.db.migrations.state import ProjectState
from google.appengine.api import datastore

# DJANGAE
from djangae.contrib import sleuth
from djangae.db.migrations import operations
from djangae.db.migrations.mapper_library import shard_query
from djangae.db.migrations.constants import MIGRATION_TASK_MARKER_KIND
from djangae.test import TestCase


class TestModel(models.Model):

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "djangae"


class OtherModel(models.Model):

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "djangae"


class OtherAppModel(models.Model):

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "testapp"


class UniqueException(Exception):
    """ An exception which we can explicity throw and catch. """
    pass


def tickle_entity(entity):
    entity['is_tickled'] = True
    datastore.Put(entity)


class MigrationOperationTests(TestCase):

    multi_db = True

    def setUp(self):
        # We need to clean out the migration task markers from the Datastore between each test, as
        # the standard flush only cleans out models
        super(MigrationOperationTests, self).setUp()
        query = datastore.Query(
            MIGRATION_TASK_MARKER_KIND,
            namespace=settings.DATABASES['default'].get('NAMESPACE', ''),
            keys_only=True
        ).Run()
        datastore.Delete([x for x in query])

    def start_operation(self, operation, detonate=True):
        # Make a from_state and a to_state to pass to the operation, these can just be the
        # current state of the models
        from_state = ProjectState.from_apps(apps)
        to_state = from_state.clone()
        schema_editor = connection.schema_editor()
        app_label = TestModel._meta.app_label

        # If we just start the operation then it will hang forever waiting for its mapper task to
        # complete, so we won't even be able to call process_task_queues().  So to avoid that we
        # detonate the _wait_until_task_finished method. Then tasks can be processed after that.
        if detonate:
            with sleuth.detonate(
                "djangae.tests.test_migrations.operations.%s._wait_until_task_finished" % operation.__class__.__name__,
                UniqueException
            ):
                try:
                    operation.database_forwards(app_label, schema_editor, from_state, to_state)
                except UniqueException:
                    pass
        else:
            operation.database_forwards(app_label, schema_editor, from_state, to_state)

    def get_entities(self, model=TestModel, namespace=None):
        namespace = namespace or settings.DATABASES['default'].get('NAMESPACE', '')
        query = datastore.Query(
            model._meta.db_table,
            namespace=namespace,
        )
        return [x for x in query.Run()]

    def test_run_operation_creates_and_updates_task_marker(self):
        """ If we run one of our custom operations, then it should create the task marker in the DB
            and defer a task, then set the marker to 'is_finished' when done.
        """
        operation = operations.AddFieldData(
            "testmodel", "new_field", models.CharField(max_length=100, default="squirrel")
        )
        self.start_operation(operation)

        # Now check that the task marker has been created.
        # Usefully, calling database_forwards() on the operation will have caused it to set the
        # `identifier` attribute on itself, meaning we can now just call _get_task_marker()
        task_marker = operation._get_task_marker()
        if task_marker is None:
            self.fail("Migration operation did not create its task marker")

        self.assertFalse(task_marker.get("is_finished"))
        self.assertNumTasksEquals(1)
        self.process_task_queues()

        # Now check that the task marker has been marked as finished
        task_marker = operation._get_task_marker()
        self.assertTrue(task_marker["is_finished"])
        self.assertNumTasksEquals(0)

    def test_starting_operation_twice_does_not_trigger_task_twice(self):
        """ If we run an operation, and then try to run it again before the task has finished
            processing, then it should not trigger a second task.
        """
        operation = operations.AddFieldData(
            "testmodel", "new_field", models.CharField(max_length=100, default="squirrel")
        )
        self.start_operation(operation)

        task_marker = operation._get_task_marker()
        self.assertFalse(task_marker["is_finished"])

        # We expect there to be a task queued for processing the operation
        self.assertNumTasksEquals(1)
        # Now try to run it again
        self.start_operation(operation)
        # We expect there to still be the same number of tasks
        self.assertNumTasksEquals(1)

    def test_running_finished_operation_does_not_trigger_new_task(self):
        """ If we re-trigger an operation which has already been run and finished, it should simply
            return without starting a new task or updating the task marker.
        """
        operation = operations.AddFieldData(
            "testmodel", "new_field", models.CharField(max_length=100, default="squirrel")
        )
        # Run the operation and check that it finishes
        with sleuth.watch("djangae.db.migrations.operations.AddFieldData._start_task") as start:
            self.start_operation(operation)
            self.assertTrue(start.called)
        task_marker = operation._get_task_marker()
        self.assertFalse(task_marker["is_finished"])
        self.assertNumTasksEquals(1)
        self.process_task_queues()
        task_marker = operation._get_task_marker()
        self.assertTrue(task_marker["is_finished"])

        # Run the operation again.  It should see that's it's finished and just return immediately.
        self.assertNumTasksEquals(0)
        with sleuth.watch("djangae.db.migrations.operations.AddFieldData._start_task") as start:
            self.start_operation(operation, detonate=False)
            self.assertFalse(start.called)
        self.assertNumTasksEquals(0)
        task_marker = operation._get_task_marker()
        self.assertTrue(task_marker["is_finished"])

    def test_addfielddata(self):
        """ Test the AddFieldData operation. """
        for x in xrange(2):
            TestModel.objects.create()

        # Just for sanity, check that none of the entities have the new field value yet
        entities = self.get_entities()
        self.assertFalse(any(entity.get("new_field") for entity in entities))

        operation = operations.AddFieldData(
            "testmodel", "new_field", models.CharField(max_length=100, default="squirrel")
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The entities should now all have the 'new_field' actually mapped over
        entities = self.get_entities()
        self.assertTrue(all(entity['new_field'] == 'squirrel' for entity in entities))

    def test_removefielddata(self):
        """ Test the RemoveFieldData operation. """
        for x in xrange(2):
            TestModel.objects.create(name="name_%s" % x)

        # Just for sanity, check that all of the entities have `name` value
        entities = self.get_entities()
        self.assertTrue(all(entity["name"] for entity in entities))

        operation = operations.RemoveFieldData(
            "testmodel", "name", models.CharField(max_length=100)
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The entities should now all have the 'name' value removed
        entities = self.get_entities()
        self.assertFalse(any(entity.get("name") for entity in entities))

    def test_copyfielddata(self):
        """ Test the CopyFieldData operation. """
        for x in xrange(2):
            TestModel.objects.create(name="name_%s" % x)

        # Just for sanity, check that none of the entities have the new "new_field" value
        entities = self.get_entities()
        self.assertFalse(any(entity.get("new_field") for entity in entities))

        operation = operations.CopyFieldData(
            "testmodel", "name", "new_field"
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The entities should now all have the "new_field" value
        entities = self.get_entities()
        self.assertTrue(all(entity["new_field"] == entity["name"] for entity in entities))

    def test_deletemodeldata(self):
        """ Test the DeleteModelData operation. """
        for x in xrange(2):
            TestModel.objects.create()

        # Just for sanity, check that the entities exist!
        entities = self.get_entities()
        self.assertEqual(len(entities), 2)

        operation = operations.DeleteModelData("testmodel")
        self.start_operation(operation)
        self.process_task_queues()

        # The entities should now all be gone
        entities = self.get_entities()
        self.assertEqual(len(entities), 0)

    def test_copymodeldata_overwrite(self):
        """ Test the CopyModelData operation with overwrite_existing=True. """

        # Create the TestModel instances, with OtherModel instances with matching PKs
        for x in xrange(2):
            instance = TestModel.objects.create(name="name_which_will_be_copied")
            OtherModel.objects.create(name="original_name", id=instance.pk)

        # Just for sanity, check that the entities exist
        testmodel_entities = self.get_entities()
        othermodel_entities = self.get_entities(model=OtherModel)
        self.assertEqual(len(testmodel_entities), 2)
        self.assertEqual(len(othermodel_entities), 2)

        operation = operations.CopyModelData(
            "testmodel", "djangae", "othermodel", overwrite_existing=True
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The OtherModel entities should now all have a name lof "name_which_will_be_copied"
        othermodel_entities = self.get_entities(model=OtherModel)
        self.assertTrue(all(
            entity["name"] == "name_which_will_be_copied" for entity in othermodel_entities
        ))

    def test_copymodeldata_no_overwrite(self):
        """ Test the CopyModelData operation with overwrite_existing=False. """

        # Create the TestModel instances, with OtherModel instances with matching PKs only for
        # odd PKs
        for x in xrange(1, 5):
            TestModel.objects.create(id=x, name="name_which_will_be_copied")
            if x % 2:
                OtherModel.objects.create(id=x, name="original_name")

        # Just for sanity, check that the entities exist
        testmodel_entities = self.get_entities()
        othermodel_entities = self.get_entities(model=OtherModel)
        self.assertEqual(len(testmodel_entities), 4)
        self.assertEqual(len(othermodel_entities), 2)

        operation = operations.CopyModelData(
            "testmodel", "djangae", "othermodel", overwrite_existing=False
        )
        self.start_operation(operation)
        self.process_task_queues()

        # We now expect there to be 4 OtherModel entities, but only the ones which didn't exist
        # already (i.e. the ones with even PKs) should have the name copied from the TestModel
        othermodel_entities = self.get_entities(model=OtherModel)
        self.assertEqual(len(othermodel_entities), 4)
        for entity in othermodel_entities:
            if entity.key().id() % 2:
                self.assertEqual(entity["name"], "original_name")
            else:
                self.assertEqual(entity["name"], "name_which_will_be_copied")

    @skipIf("ns1" not in settings.DATABASES, "This test is designed for the Djangae testapp settings")
    def test_copymodeldatatonamespace_overwrite(self):
        """ Test the CopyModelDataToNamespace operation with overwrite_existing=True. """
        ns1 = settings.DATABASES["ns1"]["NAMESPACE"]
        # Create instances, with copies in the other namespace with matching IDs
        for x in xrange(2):
            instance = TestModel.objects.create(name="name_which_will_be_copied")
            instance.save(using="ns1")

        # Just for sanity, check that the entities exist
        entities = self.get_entities()
        ns1_entities = self.get_entities(namespace=ns1)
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(ns1_entities), 2)

        operation = operations.CopyModelDataToNamespace(
            "testmodel", ns1, overwrite_existing=True
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The entities in ns1 should now all have a name lof "name_which_will_be_copied"
        ns1_entities = self.get_entities(namespace=ns1)
        self.assertTrue(all(
            entity["name"] == "name_which_will_be_copied" for entity in ns1_entities
        ))

    @skipIf("ns1" not in settings.DATABASES, "This test is designed for the Djangae testapp settings")
    def test_copymodeldatatonamespace_no_overwrite(self):
        """ Test the CopyModelDataToNamespace operation with overwrite_existing=False. """
        ns1 = settings.DATABASES["ns1"]["NAMESPACE"]
        # Create the TestModel instances, with OtherModel instances with matching PKs only for
        # odd PKs
        for x in xrange(1, 5):
            TestModel.objects.create(id=x, name="name_which_will_be_copied")
            if x % 2:
                ns1_instance = TestModel(id=x, name="original_name")
                ns1_instance.save(using="ns1")

        # Just for sanity, check that the entities exist
        entities = self.get_entities()
        ns1_entities = self.get_entities(namespace=ns1)
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(ns1_entities), 2)

        operation = operations.CopyModelDataToNamespace(
            "testmodel", ns1, overwrite_existing=False
        )
        self.start_operation(operation)
        self.process_task_queues()

        # We now expect there to be 4 entities in the new namespace, but only the ones which didn't
        # exist already (i.e. the ones with even PKs) should have their `name` updated
        ns1_entities = self.get_entities(namespace=ns1)
        self.assertEqual(len(ns1_entities), 4)
        for entity in ns1_entities:
            if entity.key().id() % 2:
                self.assertEqual(entity["name"], "original_name")
            else:
                self.assertEqual(entity["name"], "name_which_will_be_copied")

    @skipIf(
        "ns1" not in settings.DATABASES or "testapp" not in settings.INSTALLED_APPS,
        "This test is designed for the Djangae testapp settings"
    )
    def test_copymodeldatatonamespace_new_app_label(self):
        """ Test the CopyModelDataToNamespace operation with new data being saved to a new model in
            a new app as well as in a new namespace.
        """
        ns1 = settings.DATABASES["ns1"]["NAMESPACE"]
        for x in xrange(2):
            TestModel.objects.create(name="name_which_will_be_copied")

        # Just for sanity, check that the entities exist
        entities = self.get_entities()
        new_entities = self.get_entities(model=OtherAppModel, namespace=ns1)
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(new_entities), 0)

        operation = operations.CopyModelDataToNamespace(
            "testmodel", ns1, to_app_label="testapp", to_model_name="otherappmodel"
        )
        self.start_operation(operation)
        self.process_task_queues()

        # The entities in ns1 should now all have a name lof "name_which_will_be_copied"
        new_entities = self.get_entities(model=OtherAppModel, namespace=ns1)
        self.assertEqual(len(new_entities), 2)
        self.assertTrue(all(
            entity["name"] == "name_which_will_be_copied" for entity in new_entities
        ))

    def test_mapfunctiononentities(self):
        """ Test the MapFunctionOnEntities operation. """
        for x in xrange(2):
            TestModel.objects.create()
        # Test that our entities have not had our function called on them
        entities = self.get_entities()
        self.assertFalse(any(entity.get("is_tickled") for entity in entities))

        operation = operations.MapFunctionOnEntities("testmodel", tickle_entity)
        self.start_operation(operation)
        self.process_task_queues()

        entities = self.get_entities()
        self.assertEqual(len(entities), 2)
        self.assertTrue(all(entity.get("is_tickled") for entity in entities))

    def test_query_sharding(self):
        ns1 = settings.DATABASES["default"]["NAMESPACE"]

        for x in xrange(20):
            TestModel.objects.create()

        qry = datastore.Query(TestModel._meta.db_table, namespace=ns1)
        shards = shard_query(qry, 1)

        self.assertEqual(1, len(shards))
        shards = shard_query(qry, 20)

        self.assertEqual(20, len(shards))
        shards = shard_query(qry, 50)

        # We can't create 50 shards if there are only 20 objects
        self.assertEqual(20, len(shards))
