from django.conf.urls import patterns
from mapreduce.main import create_handlers_map
from djangae.utils import djangae_webapp

wrapped_urls = ((url_re.replace('.*/', '^', 1), djangae_webapp(func)) for url_re, func in create_handlers_map())
urlpatterns = patterns('', *wrapped_urls)
