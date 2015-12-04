from django.conf.urls import patterns, url, include

import djangae.contrib.mappers.urls
from . import views


urlpatterns = patterns('djangae.views',
    url(r'^start$', views.start),
    url(r'^start$', views.stop),
    url(r'^warmup$', views.warmup),
    url(r'^queue/deferred/?$', views.deferred),
    url(r'^internalupload/$', views.internalupload, name='djangae_internal_upload_handler'),
    url(r'^mapreduce/', include(djangae.contrib.mappers.urls))
)
