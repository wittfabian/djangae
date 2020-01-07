import logging
import time

try:
    # First, try to import the TestCommand from the Datastore connector project
    from gcloudc.commands.management.commands import CloudDatastoreRunner
    from django.core.management.commands.test import Command as TestCommand
except ImportError:
    class CloudDatastoreRunner:
        pass


try:
    # Now try to import the task emulator server
    from gcloud_tasks_emulator.server import create_server
    logging.info("Found the gcloud-tasks-emulator")
except ImportError:
    # Fake it if we don't have it
    logging.warning("Unable to locate the gcloud_task_emulator package. Task running will be unavailable")

    def create_server(*args, **kwargs):
        return None


class Command(CloudDatastoreRunner, TestCommand):
    USE_MEMORY_DATASTORE_BY_DEFAULT = True

    def _start_task_emulator(self):
        self.task_emulator = create_server("localhost", 9022)
        if self.task_emulator:
            print("Starting Cloud Tasks Emulator...")
            self.task_emulator.start()
            time.sleep(1)

    def _stop_task_emulator(self):
        if self.task_emulator:
            self.task_emulator.stop()

    def execute(self, *args, **kwargs):
        try:
            self._start_task_emulator()
            super().execute(*args, **kwargs)
        finally:
            self._stop_task_emulator()
