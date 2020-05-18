
from django.urls import url

from .views import oauth2callback


urlpatterns = (
    url('^oauth2callback/?', oauth2callback, name="googleauth_oauth2callback")
)
