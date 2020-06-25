import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.request import urlopen

from django.utils.autoreload import DJANGO_AUTORELOAD_ENV

from djangae.environment import get_application_root

_ACTIVE_EMULATORS = {}
_ALL_EMULATORS = ("datastore", "tasks", "storage")

_DJANGO_DEFAULT_PORT = 8080

DATASTORE_PORT = 10901
TASKS_PORT = 9022
STORAGE_PORT = 10911


def _launch_process(command_line):
    env = os.environ.copy()
    return subprocess.Popen(command_line.split(" "), env=env)


def _wait_for_tasks(port):
    time.sleep(2)  # FIXME: Need to somehow check it's running


def _wait_for_datastore(port):
    _wait(port, "Cloud Datastore Emulator")


def _wait_for_storage(port):
    _wait(port, "Cloud Storage Emulator")


def _wait(port, service):
    print("Waiting for %s..." % service)

    TIMEOUT = 60.0
    start = datetime.now()

    time.sleep(1)

    failures = 0
    while True:
        try:
            response = urlopen("http://127.0.0.1:%s/" % port)
        except (HTTPError, URLError):
            failures += 1
            time.sleep(1)
            if failures > 5:
                # Only start logging if this becomes persistent
                logging.exception("Error connecting to the %s. Retrying..." % service)
            continue

        if response.status == 200:
            # Give things a second to really boot
            time.sleep(1)
            break

        if (datetime.now() - start).total_seconds() > TIMEOUT:
            raise RuntimeError("Unable to start %s. Please check the logs." % service)

        time.sleep(1)


def start_emulators(persist_data, emulators=None, storage_dir=None, task_target_port=None, autodetect_task_port=True):
    # This prevents restarting of the emulators when Django code reload
    # kicks in
    if os.environ.get(DJANGO_AUTORELOAD_ENV) == 'true':
        return

    emulators = emulators or _ALL_EMULATORS
    storage_dir = storage_dir or os.path.join(get_application_root(), ".storage")

    if "datastore" in emulators:
        os.environ["DATASTORE_EMULATOR_HOST"] = "127.0.0.1:%s" % DATASTORE_PORT
        os.environ["DATASTORE_PROJECT_ID"] = "example"

        # Start the cloud datastore emulator
        command = "gcloud beta emulators datastore start --consistency=1.0 --quiet --project=example"
        command += " --host-port=127.0.0.1:%s" % DATASTORE_PORT

        if not persist_data:
            command += " --no-store-on-disk"

        _ACTIVE_EMULATORS["datastore"] = _launch_process(command)
        _wait_for_datastore(DATASTORE_PORT)

    if "tasks" in emulators:
        from djangae.tasks import cloud_tasks_parent_path, cloud_tasks_project, cloud_tasks_location
        default_queue = "%s/queues/default" % cloud_tasks_parent_path()

        if task_target_port is None:
            if sys.argv[1] == "runserver" and autodetect_task_port:
                from django.core.management.commands.runserver import Command as RunserverCommand
                parser = RunserverCommand().create_parser('django', 'runserver')
                args = parser.parse_args(sys.argv[2:])
                if args.addrport:
                    task_target_port = args.addrport.split(":")[-1]
                else:
                    task_target_port = _DJANGO_DEFAULT_PORT
            else:
                task_target_port = _DJANGO_DEFAULT_PORT

        command = "gcloud-tasks-emulator start -q --port=%s --target-port=%s --default-queue=%s" % (
            TASKS_PORT, task_target_port, default_queue
        )

        # If the project contains a queue.yaml, pass it to the Tasks Emulator so that those queues
        # can be created (needs version >= 0.4.0)
        queue_yaml = os.path.join(get_application_root(), "queue.yaml")
        if os.path.exists(queue_yaml):
            command += " --queue-yaml=%s --queue-yaml-project=%s --queue-yaml-location=%s" % (
                queue_yaml, cloud_tasks_project(), cloud_tasks_location()
            )

        os.environ["TASKS_EMULATOR_HOST"] = "127.0.0.1:%s" % TASKS_PORT
        _ACTIVE_EMULATORS["tasks"] = _launch_process(command)
        _wait_for_tasks(TASKS_PORT)

    if "storage" in emulators:
        os.environ["STORAGE_EMULATOR_HOST"] = "http://127.0.0.1:%s" % STORAGE_PORT
        command = "gcloud-storage-emulator start -q --port=%s" % STORAGE_PORT

        if not persist_data:
            command += " --no-store-on-disk"

        _ACTIVE_EMULATORS["storage"] = _launch_process(command)
        _wait_for_storage(STORAGE_PORT)


def stop_emulators(emulators=None):
    # This prevents restarting of the emulators when Django code reload
    # kicks in
    if os.environ.get(DJANGO_AUTORELOAD_ENV) == 'true':
        return

    emulators = emulators or _ALL_EMULATORS
    for k, v in _ACTIVE_EMULATORS.items():
        if k in emulators:
            v.kill()
