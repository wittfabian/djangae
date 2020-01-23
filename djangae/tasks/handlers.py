import os
import pickle
from django.http import HttpResponse


def deferred_handler(request):
    # Make sure we set the appengine headers in the environment from the
    # request. This may happen on live by default (not sure, docs are shaky)
    # but we set them if they're not anyway for local dev
    os.environ.setdefault("HTTP_X_APPENGINE_TASKNAME", request.META.get("HTTP_X_APPENGINE_TASKNAME", ""))
    os.environ.setdefault("HTTP_X_APPENGINE_QUEUENAME", request.META.get("HTTP_X_APPENGINE_QUEUENAME", ""))
    os.environ.setdefault("HTTP_X_APPENGINE_TASKEXECUTIONCOUNT", request.META.get(
        "HTTP_X_APPENGINE_TASKEXECUTIONCOUNT", "")
    )

    callback, args, kwargs = pickle.loads(request.body)
    callback(*args, **kwargs)

    return HttpResponse("OK")
