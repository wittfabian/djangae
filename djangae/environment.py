
import os
from functools import wraps

from djangae.utils import memoized


def application_id():
    # Fallback to example on local or if this is not specified in the
    # environment already
    result = os.environ.get("GAE_APPLICATION", "e~example").split("~", 1)[-1]
    return result


def is_production_environment():
    return not is_development_environment()


def is_development_environment():
    return 'SERVER_SOFTWARE' not in os.environ or os.environ['SERVER_SOFTWARE'].startswith("Development")


def is_in_task():
    "Returns True if the request is a task, False otherwise"
    return bool(task_name()) or bool(queue_name())


def is_in_cron():
    "Returns True if the request is in a cron, False otherwise"
    return bool(os.environ.get("HTTP_X_APPENGINE_CRON"))


def queue_name():
    "Returns the name of the current task if any, else None"
    return os.environ.get("HTTP_X_APPENGINE_QUEUENAME")


def task_name():
    "Returns the name of the current task if any, else None"
    return os.environ.get("HTTP_X_APPENGINE_TASKNAME")


def task_retry_count():
    "Returns the task retry count, or None if this isn't a task"
    try:
        return int(os.environ.get("HTTP_X_APPENGINE_TASKRETRYCOUNT"))
    except (TypeError, ValueError):
        return None


def task_queue_name():
    "Returns the name of the current task queue (if this is a task) else 'default'"
    if "HTTP_X_APPENGINE_QUEUENAME" in os.environ:
        return os.environ["HTTP_X_APPENGINE_QUEUENAME"]
    else:
        return None


@memoized
def get_application_root():
    """Simply returns the BASE_DIR setting from Django"""

    from django.conf import settings  # Avoid circular
    return settings.BASE_DIR


def task_only(view_function):
    """ View decorator for restricting access to tasks (and crons) of the application
        only.
    """

    # Inline import to prevent importing Django too early
    from django.http import HttpResponseForbidden

    @wraps(view_function)
    def replacement(*args, **kwargs):
        if not any((
            is_in_task(),
            is_in_cron(),
        )):
            return HttpResponseForbidden("Access denied.")
        return view_function(*args, **kwargs)

    return replacement


def default_gcs_bucket_name():
    return "%s.appspot.com" % application_id()


def project_id():
    # Environment variable will exist on production servers
    # fallback to "example" locally if it doesn't exist
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "example")


def region_id():
    # Environment variable will exist on production servers
    # fallback to "e" locally if it doesn't exist
    return os.environ.get("GAE_APPLICATION", "e~example").split("~", 1)[0]
