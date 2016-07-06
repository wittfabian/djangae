# THIRD PARTY
from django.apps.registry import apps  # Apps
from django.conf import settings
from django.db import connection, models
from django.db.migrations.state import ProjectState
from google.appengine.api import datastore

# DJANGAE
from djangae.contrib import sleuth
from djangae.db.migrations import operations
from djangae.test import TestCase


class TestModel(models.Model):

    class Meta:
        app_label = "djangae"


class UniqueException(Exception):
    """ An exception which we can explicity throw and catch. """
    pass


class MigrationOperationTests(TestCase):

    def test_run_operation_creates_and_updates_task_marker(self):
        """ If we run one of our custom operations, then it should create the task marker in the DB
            and defer a task, then set the marker to 'is_finished' when done.
        """
        # In order to be able to check that the operation has created the marker and deferred the
        # task, we need to interupt it, which we do by making the `_wait_until_task_finished`
        # method explode
        with sleuth.detonate(
            "djangae.tests.test_migrations.operations.AddFieldData._wait_until_task_finished",
            UniqueException
        ):
            operation = operations.AddFieldData(
                "testmodel", "new_field", models.CharField(max_length=100, default="squirrel")
            )
            # Make a from_state and a to_state to pass to the operation, these can just be the
            # current state of the models
            from_state = ProjectState.from_apps(apps)
            to_state = from_state.clone()
            schema_editor = connection.schema_editor()
            app_label = TestModel._meta.app_label
            try:
                operation.database_forwards(app_label, schema_editor, from_state, to_state)
            except UniqueException:
                pass

            # Now check that the task marker has been created.
            # Usefully, calling database_forwards() on the operation will have caused it to set the
            # `identifier` attribute on itself, meaning we can now just call _get_task_marker()
            task_marker = operation._get_task_marker()
            if task_marker is None:
                self.fail("Migration operation did not create its task marker")

            self.assertFalse(task_marker.get("is_finished"))

            self.process_task_queues()

            # Now check that the task marker has been marked as finished
            task_marker = operation._get_task_marker()
            self.assertTrue(task_marker["is_finished"])
            # And check that the entities were actually mapped over
            query = datastore.Query(
                TestModel._meta.db_table,
                namespace=settings.DATABASES['default'].get('NAMESPACE', '')
            )
            entities = [x for x in query.Run()]
            self.assertTrue(all(entity['new_field'] == 'squirrel' for entity in entities))
