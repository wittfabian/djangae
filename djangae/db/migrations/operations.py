# STANDARD LIB
import logging
import time

# THIRD PARTY
from django.db.migrations.operations.base import Operation
from django.utils import timezone
from google.appengine.api.datastore import Delete, Entity, Get, Key, Put, RunInTransaction
from google.appengine.api import datastore_errors

# DJANGAE
from djangae.db.backends.appengine.caching import remove_entities_from_cache_by_key
from djangae.db.backends.appengine.commands import reserve_id
# TODO: replace me with a real mapper library.  MUST implemented functions as described though.
from . import mapper_library

from .constants import MIGRATION_TASK_MARKER_KIND, TASK_RECHECK_INTERVAL
from .utils import do_with_retry


class BaseEntityMapperOperation(Operation):
    """ Base class for operations which map over Datastore Entities, rather than Django model
        instances.
    """

    reversible = False
    reduces_to_sql = False

    def state_forwards(self, app_label, state):
        """ As all Djangae migrations are only supplements to the Django migrations, we don't need
            to do any altering of the model state.
        """
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        # Django's `migrate` command writes to stdout without a trailing line break, which means
        # that unless we print a blank line our first print statement is on the same line
        print ""   # yay

        self._set_identifider(app_label, schema_editor, from_state, to_state)
        self._set_map_kind(app_label, schema_editor, from_state, to_state)
        self._pre_map_hook(app_label, schema_editor, from_state, to_state)
        self.namespace = schema_editor.connection.settings_dict.get("NAMESPACE")

        task_marker = self._get_task_marker()
        if task_marker is not None:
            self._wait_until_task_finished(task_marker)
            return

        print "Deferring migration operation task for %s" % self.identifier
        task_marker = self._start_task()
        self._wait_until_task_finished(task_marker)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        raise NotImplementedError("Erm...?  Help?!")

    def _get_task_marker_key(self):
        return Key.from_path(MIGRATION_TASK_MARKER_KIND, self.identifier, namespace=self.namespace)

    def _get_task_marker(self):
        """ Get the unique identifier entity for this marker from the Dastastore, if it exists. """
        try:
            return Get(self._get_task_marker_key())
        except datastore_errors.EntityNotFoundError:
            return None

    def _wait_until_task_finished(self, task_marker):
        if task_marker.get('is_finished'):
            print "Task for migration operation '%s' already finished. Skipping." % self.identifier
            return
        while not task_marker.get('is_finished'):
            print "Waiting for migration operation '%s' to complete." % self.identifier
            time.sleep(TASK_RECHECK_INTERVAL)
            task_marker = Get(task_marker.key())
            if task_marker is None:
                raise Exception("Task marker for operation '%s' disappeared." % self.identifier)
        print "Migration operation '%s' completed!" % self.identifier

    def _start_task(self):

        def txn():
            task_marker = self._get_task_marker()
            assert task_marker is None, "Migration started by separate thread?"

            task_marker = Entity(
                MIGRATION_TASK_MARKER_KIND, namespace=self.namespace, name=self.identifier
            )
            task_marker['start_time'] = timezone.now()
            task_marker['is_finished'] = False
            Put(task_marker)
            mapper_library.start_mapping(
                task_marker.key(), self.map_kind, self.namespace, self
            )
            return task_marker

        return RunInTransaction(txn)

    def _wrapped_map_entity(self, entity):
        """ Wrapper for self._map_entity which removes the entity from Djangae's cache. """

        # TODO: do we need to remove it from the caches both before and aftewards? Note that other
        # threads (from the general application running) could also be modifying the entity, and
        # that we're not using Djangae's transaction managers for our stuff here.

        remove_entities_from_cache_by_key([entity.key()], self.namespace)
        # If one entity can't be processed, then don't let that prevent others being processed
        try:
            do_with_retry(self._map_entity, entity)
        except:
            logging.exception(
                "Error processing operation %s for entity %s.  Skipping.",
                self.identifier, entity.key()
            )
        if entity.key():
            # Assumign the entity hasn't been deleted and/or it's key been wiped...
            remove_entities_from_cache_by_key([entity.key()], self.namespace)


    ##############################################################################################
    #                           METHODS FOR SUBCLASSES TO IMPLEMENT
    ##############################################################################################

    def _pre_map_hook(self, app_label, schema_editor, from_state, to_state):
        """ A hook for subclasses to do anything that needs to be done before the mapping starts
            but which cannot be done in __init__ due to the need for the schema_editor/state/etc.
        """
        pass

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        """ Set self.identifier, which must be a string which uniquely identifies this operation
            across the entire site.  It must be able to fit in a Datastore string property.
            This will likely need to use app_label combined with values passed to __init__.
        """
        raise NotImplementedError(
            "Subclasses of EntityMapperOperation must implement _set_identifider"
        )

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        """ Set an attribute 'map_kind' of the 'kind' of Datastore Entities to be mapped over. """
        raise NotImplementedError(
            "Subclasses of EntityMapperOperation must implement _set_map_kind"
        )

    def _map_entity(self, entity):
        """ Hook for subclasses to implement.  This is called for every Entity and should do
            whatever data manipulation is necessary.  Note that whatever you do to the entity
            must be done transactionally; this is not wrapped in a transaction.
        """
        raise NotImplementedError("Subclasses of EntityMapperOperation must implement _map_entity")


class AddFieldData(BaseEntityMapperOperation):

    def __init__(self, model_name, name, field):
        self.model_name = model_name
        self.name = name
        self.field = field

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s" % (
            app_label, self.model_name, self.__class__.__name__, self.name
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as
        # it's possible that 2 operations add the same field to the same model, e.g. if it is
        # added, then removed, then added.  Although it's highly unlikely that those 2 migrations
        # would ever run at the same time, so we can probably ignore it for now :-).
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _map_entity(self, entity):
        column_name = self.field.db_column or self.name
        # Call get_default() separately for each entity, in case it's a callable like timezone.now
        value = self.field.get_default()

        def txn(entity):
            entity = Get(entity.key())
            entity[column_name] = value
            Put(entity)

        RunInTransaction(txn, entity)


class RemoveFieldData(BaseEntityMapperOperation):

    def __init__(self, model_name, name, field):
        self.model_name = model_name
        self.name = name
        self.field = field

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s" % (
            app_label, self.model_name, self.__class__.__name__, self.name
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as
        # it's possible that 2 operations add the same field to the same model, e.g. if it is
        # added, then removed, then added.  Although it's highly unlikely that those 2 migrations
        # would ever run at the same time, so we can probably ignore it for now :-).
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _map_entity(self, entity):
        column_name = self.field.db_column or self.name

        def txn(entity):
            entity = Get(entity.key())
            try:
                del entity[column_name]
            except KeyError:
                return
            Put(entity)

        RunInTransaction(txn, entity)


class CopyFieldData(BaseEntityMapperOperation):

    def __init__(self, model_name, from_column_name, to_column_name):
        self.model_name = model_name
        self.from_column_name = from_column_name
        self.to_column_name = to_column_name

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s" % (
            app_label, self.model_name, self.__class__.__name__,
            self.from_column_name, self.to_column_name
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as per
        # other operations
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _map_entity(self, entity):

        def txn(entity):
            entity = Get(entity.key())
            try:
                entity[self.to_column_name] = entity[self.from_column_name]
            except KeyError:
                return
            Put(entity, entity)

        RunInTransaction(txn)


class DeleteModelData(BaseEntityMapperOperation):

    def __init__(self, model_name):
        self.model_name = model_name

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s" % (
            app_label, self.model_name, self.__class__.__name__
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as per
        # other operations
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _map_entity(self, entity):
        try:
            Delete(entity.key())
        except datastore_errors.EntityNotFoundError:
            return


class CopyModelData(BaseEntityMapperOperation):
    """ Copies entities from one entity kind to another. """

    def __init__(
        self, model_name, to_model_app_label, to_model_name,
        overwrite_existing=False
    ):
        self.model_name = model_name
        self.to_model_app_label = to_model_app_label
        self.to_model_name = to_model_name
        self.overwrite_existing = overwrite_existing

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s.%s" % (
            app_label, self.model_name, self.__class__.__name__,
            self.to_model_app_label, self.to_model_name
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as per
        # other operations
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        """ We need to map over the entities that we're copying *from*. """
        model = to_state.apps.get_model(self.app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _pre_map_hook(self, app_label, schema_editor, from_state, to_state):
        self.to_kind = to_state.apps.get_model(self.to_model_app_label, self.to_model_name)

    def _map_entity(self, entity):
        new_key = Key(self.to_kind, entity.key().id_or_name, namespace=self.namespace)

        def txn():
            existing = Get(new_key)
            if existing and not self.overwrite_existing:
                return
            if isinstance(entity.key().id_or_name(), (int, long)):
                reserve_id(self.to_model_kind, entity.key().id_or_name(), self.namespace)
            new_entity = entity.copy()
            new_entity._Entity__key = new_key
            Put(new_entity)

        RunInTransaction(txn)


class CopyModelDataToNamespace(BaseEntityMapperOperation):
    """ Copies entities from one Datastore namespace to another. """

    def __init__(
        self, model_name, to_namespace, to_model_app_label=None, to_model_name=None,
        overwrite_existing=False
    ):
        self.model_name = model_name
        self.to_namespace = to_namespace
        self.to_model_app_label = to_model_app_label
        self.to_model_name = to_model_name
        self.overwrite_existing = overwrite_existing

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s.%s" % (
            app_label, self.model_name, self.__class__.__name__, self.to_namespace
        )
        if self.to_model_app_label:
            identifier += (".%s" % self.to_model_app_label)
        if self.to_model_name:
            identifier += (".%s" % self.to_model_name)
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as per
        # other operations
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        """ We need to map over the entities that we're copying *from*. """
        model = to_state.apps.get_model(self.app_label, self.model_name)
        self.map_kind = model._meta.db_table

    def _pre_map_hook(self, app_label, schema_editor, from_state, to_state):
        to_model_app_label = self.to_model_app_label or app_label
        to_model_name = self.to_model_name or self.model_name
        self.to_kind = to_state.apps.get_model(to_model_app_label, to_model_name)

    def _map_entity(self, entity):
        new_key = Key(self.to_kind, entity.key().id_or_name, namespace=self.to_namespace)

        def txn():
            existing = Get(new_key)
            if existing and not self.overwrite_existing:
                return
            if isinstance(entity.key().id_or_name(), (int, long)):
                reserve_id(self.to_model_kind, entity.key().id_or_name(), self.to_namespace)
            new_entity = entity.copy()
            new_entity._Entity__key = new_key
            Put(new_entity)

        RunInTransaction(txn)


class MapFunctionOnEntities(BaseEntityMapperOperation):
    """ Operation for calling a custom function on each entity of a given model. """

    def __init__(self, model_name, function):
        self.model_name = model_name
        self.function = function

    def _set_identifider(self, app_label, schema_editor, from_state, to_state):
        identifier = "%s.%s.%s:%s" % (
            app_label, self.model_name, self.__class__.__name__, self.function.__name__
        )
        # TODO: ideally we need some kind of way of getting hold of the migration name here, as per
        # other operations
        self.identifier = identifier

    def _set_map_kind(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        kind = model._meta.db_table
        self.map_kind = kind

    def _map_entity(self, entity):
        self.function(entity)
