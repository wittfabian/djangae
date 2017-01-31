from django.conf.urls import url
from djangae.utils import djangae_webapp

from django.views.decorators.csrf import csrf_exempt

from mapreduce.main import create_handlers_map as mapreduce_handlers

urlpatterns = [
    url(url_re.replace('.*/', '^', 1), csrf_exempt(djangae_webapp(func)))
    for url_re, func in mapreduce_handlers()
]
