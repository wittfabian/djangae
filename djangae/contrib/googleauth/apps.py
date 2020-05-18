from django.apps import AppConfig


class GoogleauthConfig(AppConfig):
    name = 'googleauth'
    verbose_name = "Googleauth"

    def ready(self):
        from .models import AppOAuthCredentials
        AppOAuthCredentials.get_or_create()
