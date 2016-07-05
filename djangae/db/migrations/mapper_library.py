# Skeleton layout of what the mapping library that we use will need to do


###################################################################################################
#
#
#                 THIS IS NOT "REAL" CODE.  REPLACE WITH A PROPER MAPPING LIBRARY!
#
#
#
###################################################################################################


from django.utils import timezone
from google.appengine.api import datastore
from google.appengine.ext import deferred


def start_mapping(task_marker_key, kind, namespace, operation):
    """ This must *transactionally* defer a task which will call `operation._wrapped_map_entity` on
        all entities of the given `kind` in the given `namespace` and will then transactionally
        update the entity of the given `task_marker_key_key` with `is_finished=True` after all
        entities have been mapped.
    """
    # The reason for taking an `operation` object and calling `_wrapped_map_entity` on it is that
    # instance methods cannot be pickled, but we can pickle the object and then call a method on it
    deferred.defer(do_mapping, task_marker_key, kind, namespace, operation, _transactional=True)


def do_mapping(task_marker_key, kind, namespace, operation):

    method = getattr(operation, '_wrapped_map_entity')

    results = datastore.Query(kind, namespace=namespace).Run()
    for entity in results:
        method(entity)

    def finish(task_marker_key):
        task_marker = datastore.Get(task_marker_key)
        task_marker['finish_time'] = timezone.now()
        task_marker['is_finished'] = True
        datastore.Put(task_marker)

    datastore.RunInTransaction(finish, task_marker_key)
