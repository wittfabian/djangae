from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DjangaeTasksConfig(AppConfig):
    name = "djangae.tasks"
    verbose_name = "Djangae Tasks"

    def ready(self):
        """
            On startup we ensure the required queues
            exist based on settings.CLOUD_TASKS_QUEUES
        """
        from . import ensure_required_queues_exist
        ensure_required_queues_exist()

        if not getattr(settings, "CLOUD_TASKS_LOCATION", None):
            raise ImproperlyConfigured(
                "You must specify settings.CLOUD_TASKS_LOCATION "
                "to use the djangae.tasks app."
            )
