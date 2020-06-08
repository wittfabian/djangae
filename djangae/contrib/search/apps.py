
from django.apps import AppConfig


class SearchConfig(AppConfig):
    name = 'djangae.contrib.search'
    verbose_name = "Search"

    def ready(self):
        pass
