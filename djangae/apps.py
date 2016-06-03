from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ImproperlyConfigured


class DjangaeConfig(AppConfig):
    name = 'djangae'
    verbose_name = _("Djangae")

    def ready(self):
        from djangae.db.backends.appengine.caching import reset_context
        from django.core.signals import request_finished, request_started

        request_finished.connect(reset_context, dispatch_uid="request_finished_context_reset")
        request_started.connect(reset_context, dispatch_uid="request_started_context_reset")

        from django.conf import settings
        contenttype_configuration_error = ImproperlyConfigured(
            "If you're using django.contrib.contenttypes, then you need "
            "to add djangae.contrib.contenttypes to INSTALLED_APPS after "
            "django.contrib.contenttypes."
        )
        if 'django.contrib.contenttypes' in settings.INSTALLED_APPS:
            if not 'djangae.contrib.contenttypes' in settings.INSTALLED_APPS:
                # Raise error if User is using Django CT, but not Djangae
                raise contenttype_configuration_error
            else:
                if settings.INSTALLED_APPS.index('django.contrib.contenttypes') > \
                        settings.INSTALLED_APPS.index('djangae.contrib.contenttypes'):
                    # Raise error if User is using both Django and Djangae CT, but
                    # Django CT comes after Djangae CT
                    raise contenttype_configuration_error
