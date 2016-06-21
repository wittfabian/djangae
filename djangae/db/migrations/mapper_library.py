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


def start_mapping(task_marker, kind, namespace, function):
    """ This must *transactionally* defer a task which will call `function` on all entities of the
        given `kind` in the given `namespace` and will then transactionally update the given
        `task_marker` with `is_finished=True` after all entities have been mapped.
    """
    deferred.defer(do_mapping, task_marker, kind, namespace, function, _transactional=True)


def do_mapping(task_marker, kind, namespace, function):
    results = datastore.Query(kind, namespace=namespace).Run()
    for entity in results:
        function(entity)

    def finish(task_marker):
        task_marker = datastore.Get(task_marker.key())
        task_marker['finish_timie'] = timezone.now()
        task_marker['is_finished'] = True
        datastore.Put(entity)

    datastore.RunInTransaction(finish, task_marker)
