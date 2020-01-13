from django.conf import settings
from djangae import environment

import os
import grpc

default_app_config = 'djangae.tasks.apps.DjangaeTasksConfig'

CLOUD_TASKS_PROJECT_SETTING = "CLOUD_TASKS_PROJECT_ID"
CLOUD_TASKS_LOCATION_SETTING = "CLOUD_TASKS_LOCATION"


def get_cloud_tasks_client():
    """
        Get an instance of a Google CloudTasksClient

        Note. Nested imports are to allow for things not to
        force the google cloud tasks dependency if you're not
        using it
    """
    from google.cloud.tasks_v2 import CloudTasksClient

    is_app_engine = os.environ.get("GAE_ENV") == "standard"

    if is_app_engine:
        from google.auth import app_engine
        return CloudTasksClient(credentials=app_engine.Credentials())
    else:
        # Running locally, try to connect to the emulator

        from google.cloud.tasks_v2.gapic.transports.cloud_tasks_grpc_transport import CloudTasksGrpcTransport
        from google.api_core.client_options import ClientOptions

        port = 9022  # FIXME: Pass this somehow
        client = CloudTasksClient(
            transport=CloudTasksGrpcTransport(channel=grpc.insecure_channel("127.0.0.1:%s" % port)),
            client_options=ClientOptions(api_endpoint="127.0.0.1:%s" % port)
        )
        return client


def ensure_required_queues_exist():
    """
        Reads settings.CLOUD_TASK_QUEUES_REQUIRED
        and calls create_queue for them if they don't exist
    """
    client = get_cloud_tasks_client()

    for queue in getattr(settings, "CLOUD_TASKS_QUEUES", []):
        client.create_queue(queue["name"])


def cloud_tasks_project():
    project_id = getattr(settings, CLOUD_TASKS_PROJECT_SETTING, None)
    if not project_id:
        project_id = environment.project_id()

    return project_id


def cloud_tasks_parent_path():
    """
        Returns the path based on settings.CLOUD_TASK_PROJECT_ID
        and settings.CLOUD_TASK_LOCATION_ID. If these are
        unset, uses the project ID from the environment
    """

    location_id = getattr(settings, CLOUD_TASKS_LOCATION_SETTING, None)
    project_id = cloud_tasks_project()

    assert(project_id)
    assert(location_id)

    return "projects/%s/locations/%s" % (
        project_id, location_id
    )


def cloud_tasks_queue_path(queue_name, parent=None):
    """
        Returns a cloud tasks path to a queue, if parent
        is passed it uses that as a base, otherwise
        uses the result of cloud_tasks_parent_path()
    """

    return "%s/queues/%s" % (
        parent or cloud_tasks_parent_path(),
        queue_name
    )
