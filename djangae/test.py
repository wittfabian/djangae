import contextlib
import logging

from django import test
from django.test import Client

from google.appengine.api import apiproxy_stub_map
from google.appengine.datastore import datastore_stub_util


@contextlib.contextmanager
def inconsistent_db(probability=0, connection='default'):
    """
        A context manager that allows you to make the datastore inconsistent during testing.
        This is vital for writing applications that deal with the Datastore's eventual consistency
    """

    from django.db import connections

    conn = connections[connection]

    if not hasattr(conn.creation, "testbed") or "datastore_v3" not in conn.creation.testbed._enabled_stubs:
        raise RuntimeError("Tried to use the inconsistent_db stub when not testing")


    stub = apiproxy_stub_map.apiproxy.GetStub('datastore_v3')

    # Set the probability of the datastore stub
    original_policy = stub._consistency_policy
    stub.SetConsistencyPolicy(datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=probability))
    try:
        yield
    finally:
        # Restore to consistent mode
        stub.SetConsistencyPolicy(original_policy)


def _get_queued_tasks(stub, queue_name=None, flush=True):
    tasks = []

    for queue in stub.GetQueues():
        for task in stub.GetTasks(queue['name']):
            if queue_name is None or queue_name == queue['name']:
                tasks.append(task)

        if flush:
            stub.FlushQueue(queue["name"])

    return tasks

def _flush_tasks(stub, queue_name=None):
    if queue_name:
        stub.FlushQueue(queue_name)
    else:
        for queue in stub.GetQueues():
            stub.FlushQueue(queue["name"])

def process_task_queues(queue_name=None):
    """
        Processes any queued tasks inline without a server.
        This is useful for end-to-end testing background tasks.
    """

    stub = apiproxy_stub_map.apiproxy.GetStub("taskqueue")

    tasks = _get_queued_tasks(stub, queue_name)

    client = Client() # Instantiate a test client for processing the tasks

    while tasks:
        task = tasks.pop(0) # Get the first task

        decoded_body = task['body'].decode('base64')
        post_data = decoded_body
        headers = { "HTTP_{}".format(x.replace("-", "_").upper()): y for x, y in task['headers'] }

        #FIXME: set headers like the queue name etc.
        method = task['method']

        if method.upper() == "POST":
            #Fixme: post data?
            response = client.post(task['url'], data=post_data, content_type=headers['HTTP_CONTENT_TYPE'], **headers)
        else:
            response = client.get(task['url'], **headers)

        if response.status_code != 200:
            logging.info("Unexpected status ({}) while simulating task with url: {}".format(response.status_code, task['url']))

        if not tasks:
            #The map reduce may have added more tasks, so refresh the list
            tasks = _get_queued_tasks(stub, queue_name)

class TestCase(test.TestCase):
    def setUp(self):
        super(TestCase, self).setUp()
        self.taskqueue_stub = apiproxy_stub_map.apiproxy.GetStub("taskqueue")
        if self.taskqueue_stub:
            _flush_tasks(self.taskqueue_stub) # Make sure we clear the queue before every test

    def assertNumTasksEquals(self, num, queue_name='default'):
        self.assertEqual(num, len(_get_queued_tasks(self.taskqueue_stub, queue_name, flush=False)))

    def process_task_queues(self, queue_name=None):
        process_task_queues(queue_name)
