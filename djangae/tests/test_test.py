from google.appengine.ext import deferred

from djangae.test import TestCase, _get_queued_tasks


def my_task():
    """
    Basic task for testing task queues.
    """
    pass


class TaskQueueTests(TestCase):

    def test_get_queued_tasks_flush(self):
        deferred.defer(my_task)
        deferred.defer(my_task, _queue='another')

        # We don't use self.assertNumTasksEquals here because we want to flush.
        tasks = _get_queued_tasks(self.taskqueue_stub, queue_name='default')
        self.assertEqual(1, len(tasks))

        tasks = _get_queued_tasks(self.taskqueue_stub, queue_name='another')
        self.assertEqual(1, len(tasks))

        tasks = _get_queued_tasks(self.taskqueue_stub)
        self.assertEqual(0, len(tasks))
