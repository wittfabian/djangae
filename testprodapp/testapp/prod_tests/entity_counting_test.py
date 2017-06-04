import datetime

from google.appengine.ext import deferred

from ..models import TestResult
from ..models import Uuid


def _test_count(method, name, pivot=None, use_gt=False):
    result_key = 'count.{0}().{1}'.format(method, name)
    TestResult.objects.set_result(result_key, 'started', -1, {})
    if pivot is None:
        query = Uuid.objects.all()
    elif use_gt:
        query = Uuid.objects.filter(value__gte=pivot)
    else:
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


def test_entity_count_vs_length(create=True):
    if create:
        Uuid.objects.create_entities()
    deferred.defer(_test_count, 'len', 'all')
    deferred.defer(_test_count, 'len', 'lt8', pivot='8', use_gt=False)
    deferred.defer(_test_count, 'len', 'gt8', pivot='8', use_gt=True)
    deferred.defer(_test_count, 'count', 'all')
    deferred.defer(_test_count, 'count', 'lt8', pivot='8', use_gt=False)
    deferred.defer(_test_count, 'count', 'gt8', pivot='8', use_gt=True)
