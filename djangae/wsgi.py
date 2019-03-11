

class DjangaeApplication(object):

    def __init__(self, application):
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        for app in settings.INSTALLED_APPS:
            if app.startswith("django."):
                raise ImproperlyConfigured("You must place 'djangae' before any 'django' apps in INSTALLED_APPS")
            elif app == "djangae":
                break

        self.wrapped_app = application

    def __call__(self, environ, start_response):
        return self.wrapped_app(environ, start_response)
