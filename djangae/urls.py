from django.conf.urls import patterns, url, include
import djangae.contrib.pipelines.urls
import djangae.contrib.mapreduce.urls

urlpatterns = patterns('djangae.views',
    url(r'^start$', 'start'),
    url(r'^stop$', 'stop'),
    url(r'^warmup$', 'warmup'),
    url(r'^queue/deferred/?$', 'deferred'),
    url(r'^internalupload/$', 'internalupload', name='djangae_internal_upload_handler'),
    url(r'^pipeline/', include(djangae.contrib.pipelines.urls)),
    url(r'^mapreduce/', include(djangae.contrib.mapreduce.urls)),
)
