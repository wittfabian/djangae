
import os
from django.test import LiveServerTestCase

from djangae.tasks import (
    cloud_tasks_parent_path,
    cloud_tasks_queue_path,
    ensure_required_queues_exist,
    get_cloud_tasks_client,
)
from google.api_core.exceptions import GoogleAPIError


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
    def __init__(self, *args, **kwargs):
        self.max_task_retry_count = 100
        super().__init__(*args, **kwargs)

    def setUp(self):
        # Create all the queues required by this application

        super().setUp()

        # Find the port we were allocated
        port = self.live_server_url.rsplit(":")[-1]

        # Set that in the environment variable used by the Cloud Tasks Emulator
        os.environ["APP_ENGINE_TARGET_PORT"] = port

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

            tasks = [x for x in self.task_client.list_tasks(path)]
            while tasks:
                task = tasks.pop(0)

                try:
                    self.task_client.run_task(task.name)
                except GoogleAPIError as e:
                    if failure_behaviour == TaskFailedBehaviour.RETRY_TASK:
                        if not hasattr(task, "_failed_count"):
                            task._failed_count = 1
                        else:
                            task._failed_count += 1

                        if task._failed_count >= self.max_task_retry_count:
                            # Make sure we don't get an infinite loop while retrying
                            raise

                        tasks.append(task)  # Add back to the end of the queue
                        continue
                    elif failure_behaviour == TaskFailedBehaviour.RAISE_ERROR:
                        raise TaskFailedError(task.name, str(e))
                    else:
                        # Do nothing, ignore the failure
                        pass

                if not tasks:
                    tasks = [x for x in self.task_client.list_tasks(path)]
