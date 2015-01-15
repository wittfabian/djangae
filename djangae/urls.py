from django.conf.urls import patterns, url, include
import djangae.contrib.mappers.urls

from djangae.views import warmup, deferred

urlpatterns = patterns('djangae.views',
    url(r'^warmup$', warmup),
    url(r'^queue/deferred/?$', deferred),
    url(r'^mapreduce/', include(djangae.contrib.mappers.urls))
)
