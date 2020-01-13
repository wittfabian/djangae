
from django.test import LiveServerTestCase

from djangae.tasks import (
    ensure_required_queues_exist,
    get_cloud_tasks_client,
    cloud_tasks_parent_path,
    cloud_tasks_queue_path
)


class TaskFailedBehaviour:
    DO_NOTHING = 0
    RETRY_TASK = 1
    RAISE_ERROR = 2


class TaskFailedError(Exception):
    def __init__(self, task_name, status_code, original_exception=None):
        self.task_name = task_name
        self.status_code = status_code
        self.original_exception = original_exception

        super(TaskFailedError, self).__init__(
            "Task {} failed with status code: {}. \n\nMessage was: {}".format(
                task_name, status_code, original_exception
            )
        )


class TestCaseMixin(LiveServerTestCase):
    """
        A TestCase base class that manages task queues
        during testing. Ensures that required queues
        are created and paused, and manually runs the
        queued tasks in them to check their responses
    """

    def setUp(self):
        # Create all the queues required by this application
        ensure_required_queues_exist()

        self.task_client = get_cloud_tasks_client()

        parent = cloud_tasks_parent_path()

        for queue in self.task_client.list_queues(parent=parent):
            # Make sure the queue is paused
            self.task_client.pause_queue(queue.name)

            # Make sure it's empty
            self.task_client.purge_queue(queue.name)

    def _get_queues(self, queue_name=None):
        if queue_name:
            path = cloud_tasks_queue_path(queue_name)
            queue = self.task_client.get_queue(path)
            queues = [queue]
        else:
            parent = cloud_tasks_parent_path()
            queues = self.task_client.list_queues(parent)

        return queues

    def flush_task_queues(self, queue_name=None):
        for queue in self._get_queues(queue_name=queue_name):
            self.task_client.purge_queue(queue.name)

    def get_task_count(self, queue_name=None):
        path = cloud_tasks_queue_path(queue_name)

        return sum([
            len(list(self.task_client.list_tasks(path)))
            for queue in self._get_queues(queue_name=queue_name)
        ])

    def process_task_queues(self, queue_name=None, failure_behaviour=TaskFailedBehaviour.RAISE_ERROR):
        parent = cloud_tasks_parent_path()
        for queue in self.task_client.list_queues(parent=parent):
            path = queue.name

            for task in self.task_client.list_tasks(path):
                response = self.task_client.run_task(task.name)
                if failure_behaviour == TaskFailedBehaviour.RETRY_TASK:
                    while str(response.status_code)[0] != "2":
                        response = self.task_client.run_task(task.name)
                elif failure_behaviour == TaskFailedBehaviour.RAISE_ERROR:
                    if not str(response.status_code)[0] != "2":
                        raise TaskFailedError(task.name, response.status)
                else:
                    pass
