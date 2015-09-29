from django.conf.urls import patterns, url, include
import djangae.contrib.mappers.urls

urlpatterns = patterns('djangae.views',
    url(r'^start$', 'start'),
    url(r'^start$', 'stop'),
    url(r'^warmup$', 'warmup'),
    url(r'^queue/deferred/?$', 'deferred'),
    url(r'^internalupload/$', 'internalupload', name='djangae_internal_upload_handler'),
    url(r'^mapreduce/', include(djangae.contrib.mappers.urls))
)
