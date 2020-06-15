
import os
from functools import wraps

from djangae.utils import memoized
from django.http import HttpResponseForbidden

# No SDK imports allowed in module namespace because `./manage.py runserver`
# imports this before the SDK is added to sys.path. See bugs #899, #1055.


def application_id():
    # Fallback to example on local or if this is not specified in the
    # environment already
    result = os.environ.get("GAE_APPLICATION", "e~example").split("~", 1)[-1]
    return result


def is_production_environment():
    return not is_development_environment()


def is_development_environment():
    return 'GAE_ENV' not in os.environ or os.environ['GAE_ENV'] != 'standard'


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
    """Traverse the filesystem upwards and return the directory containing app.yaml"""
    from django.conf import settings  # Avoid circular

    path = os.path.dirname(os.path.abspath(__file__))
    app_yaml_path = os.environ.get('DJANGAE_APP_YAML_LOCATION', None)

    # If the DJANGAE_APP_YAML_LOCATION variable is setup, will try to locate
    # it from there.
    if (app_yaml_path is not None and
            os.path.exists(os.path.join(app_yaml_path, "app.yaml"))):
        return app_yaml_path

    # Failing that, iterates over the parent folders until it finds it,
    # failing when it gets to the root
    while True:
        if os.path.exists(os.path.join(path, "app.yaml")):
            return path
        else:
            parent = os.path.dirname(path)
            if parent == path:  # Filesystem root
                break
            else:
                path = parent

    # Use the Django base directory as a fallback. We search for app.yaml
    # first because that will be the "true" root of the GAE app
    return settings.BASE_DIR


def task_only(view_function):
    """ View decorator for restricting access to tasks (and crons) of the application
        only.
    """

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
