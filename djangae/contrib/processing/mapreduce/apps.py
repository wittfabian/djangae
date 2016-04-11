from __future__ import absolute_import

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _


class MapreduceConfig(AppConfig):
    name = 'mapreduce'
    verbose_name = _("Mapreduce")

    def ready(self):
        try:
            import mapreduce
        except ImportError:
            raise ImproperlyConfigured(
                "To use djangae.contrib.processing.mapreduce you must have the "
                "AppEngineMapreduce library installed."
            )
