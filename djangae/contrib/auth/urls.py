from django.conf.urls import patterns, url

urlpatterns = patterns('djangae.contrib.auth.views',
    url(r'^login_redirect$', 'login_redirect', name='djangae_login_redirect'),
)