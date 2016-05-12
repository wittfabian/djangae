# THIRD PARTY
from django.conf.urls import patterns, url

# DJANGAE
from djangae.contrib.lock.views import cleanup_locks


urlpatterns = patterns('',
    url(r'^cleanup-locks/$', cleanup_locks, name="cleanup_locks"),
)
