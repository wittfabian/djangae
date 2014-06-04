from django.conf.urls import patterns, url

urlpatterns = patterns('djangae.views',
    url(r'^warmup$', 'djangae.views.warmup'),
    url(r'^queue/deferred/?$', 'djangae.views.deferred')
)