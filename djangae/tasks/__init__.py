import os


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
