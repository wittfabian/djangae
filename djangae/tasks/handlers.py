import pickle
from django.http import HttpResponse


def deferred_handler(request):
    callback, args, kwargs = pickle.loads(request.body)
    callback(*args, **kwargs)
    return HttpResponse("OK")
