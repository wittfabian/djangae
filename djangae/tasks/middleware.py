import os


def task_environment_middleware(get_response):
    def middleware(request):
        # Make sure we set the appengine headers in the environment from the
        # request.
        try:
            os.environ["HTTP_X_APPENGINE_TASKNAME"] = request.META.get("HTTP_X_APPENGINE_TASKNAME", "")
            os.environ["HTTP_X_APPENGINE_QUEUENAME"] = request.META.get("HTTP_X_APPENGINE_QUEUENAME", "")
            os.environ["HTTP_X_APPENGINE_TASKEXECUTIONCOUNT"] = request.META.get(
                "HTTP_X_APPENGINE_TASKEXECUTIONCOUNT", ""
            )

            return get_response(request)
        finally:
            os.environ.pop("HTTP_X_APPENGINE_TASKNAME", None)
            os.environ.pop("HTTP_X_APPENGINE_QUEUENAME", None)
            os.environ.pop("HTTP_X_APPENGINE_TASKEXECUTIONCOUNT", None)

    return middleware
