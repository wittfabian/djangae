from django.apps import AppConfig
from django.db.models.signals import post_migrate


class GAuthConfig(AppConfig):

   name = "djangae.contrib.gauth"
   verbose_name = "gauth"

   def ready(self):
        from gauth.datastore.models import lazy_permission_creation

        post_migrate.disconnect(
            dispatch_uid="django.contrib.auth.management.create_permissions")
        post_migrate.connect(
            lazy_permission_creation,
            sender=self,
            dispatch_uid="django.contrib.auth.management.create_permissions",
        )
