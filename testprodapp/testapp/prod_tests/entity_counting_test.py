import datetime

from google.appengine.ext import deferred

from ..models import TestResult
from ..models import Uuid


def _test_count(batch_id, method, name, pivot=None, use_gt=False):
    result_key = 'count.{0}.{1}'.format(method, name)
    TestResult.objects.set_result(result_key, 'started', -1, {})

    query = Uuid.objects.filter(batch_uuid=batch_id)

    if pivot and use_gt:
        query = Uuid.objects.filter(value__gte=pivot)
    elif pivot:
        query = Uuid.objects.filter(value__lt=pivot)

    start = datetime.datetime.now()
    if method == 'len':
        result = len(query)
    elif method == 'count':
        result = query.count()
    else:
        raise Exception('unknown counting method')

    end = datetime.datetime.now()
    duration = (end - start).total_seconds()

    TestResult.objects.set_result(
        result_key,
        'success',
        duration,
        dict(start=start, end=end, duration=duration, count=result),
    )


def _clear_batch(batch_id):
    Uuid.objects.filter(batch_uuid=batch_id).delete()


def test_entity_count_vs_length():
    batch_id = Uuid.objects.create_entities()

    deferred.defer(_test_count, batch_id, 'len', 'all')
    deferred.defer(_test_count, batch_id, 'len', 'lt8', pivot='8', use_gt=False)
    deferred.defer(_test_count, batch_id, 'len', 'gt8', pivot='8', use_gt=True)
    deferred.defer(_test_count, batch_id, 'count', 'all')
    deferred.defer(_test_count, batch_id, 'count', 'lt8', pivot='8', use_gt=False)
    deferred.defer(_test_count, batch_id, 'count', 'gt8', pivot='8', use_gt=True)

    # Clean up the created objects after the 10 minute task deadline
    deferred.defer(_clear_batch, batch_id, _countdown=10 * 60)
