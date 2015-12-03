from django.conf.urls import patterns, url

urlpatterns = patterns(
    'djangae.contrib.gauth.views',
    url(r'^login_redirect$', 'login_redirect', name='djangae_login_redirect'),
    url(r'^switch_accounts/$', 'switch_accounts', name='djangae_switch_accounts'),
)
