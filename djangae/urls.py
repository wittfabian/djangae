from django.conf import settings
from django.conf.urls import url, include

from . import views


urlpatterns = [
    url(r'^start$', views.start),
    url(r'^stop$', views.stop),
    url(r'^warmup$', views.warmup),
    url(r'^clearsessions$', views.clearsessions),
]
