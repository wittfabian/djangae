from django.http import HttpResponse


def deferred_handler(request):
    return HttpResponse("OK")
