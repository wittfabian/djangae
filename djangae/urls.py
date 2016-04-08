from django.conf.urls import url, include
import djangae.contrib.processing.pipelines.urls
import djangae.contrib.processing.mapreduce.urls

from . import views


urlpatterns = [
    url(r'^start$', views.start),
    url(r'^stop$', views.stop),
    url(r'^warmup$', views.warmup),
    url(r'^queue/deferred/?$', views.deferred),
    url(r'^internalupload/$', views.internalupload, name='djangae_internal_upload_handler'),
    url(r'^pipeline/', include(djangae.contrib.processing.pipelines.urls)),
    url(r'^mapreduce/', include(djangae.contrib.processing.mapreduce.urls)),
]
