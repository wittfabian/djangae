
from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class SearchConfig(AppConfig):
    name = 'djangae.contrib.search'
    verbose_name = "Search"

    def ready(self):
        try:
            import nltk  # noqa
        except ImportError:
            raise ImproperlyConfigured(
                "djangae.contrib.search depends on the nltk library, which is not installed"
            )
