from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from gcloudc.db.models.fields.iterable import SetField

from .permissions import PermissionChoiceField


class User(AbstractBaseUser):
    pass


class UserPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permissions")
    permission = PermissionChoiceField()
    obj_id = models.PositiveIntegerField()


class Group(models.Model):
    name = models.CharField(_('name'), max_length=150, unique=True)
    permissions = SetField(
        PermissionChoiceField(),
        blank=True
    )

    def __str__(self):
        return self.name


class AppOAuthCredentials(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    client_id = models.CharField(max_length=150, default="")
    client_secret = models.CharField(max_length=150, default="")

    @classmethod
    def get(cls):
        from djangae.environment import application_id
        return cls.objects.get(
            pk=application_id()
        )

    @classmethod
    def get_or_create(cls, **kwargs):
        from djangae.environment import application_id
        return cls.objects.get_or_create(
            pk=application_id(),
            defaults=kwargs
        )[0]


# Set in the Django session in the oauth2callback. This is used
# by the backend's authenticate() method
_OAUTH_USER_SESSION_SESSION_KEY = "_OAUTH_USER_SESSION_ID"


class OAuthUserSession(models.Model):
    email_address = models.EmailField(primary_key=True)
    authorization_code = models.CharField(max_length=150)

    access_token = models.CharField(max_length=150, blank=True)
    refresh_token = models.CharField(max_length=150, blank=True)

    def is_valid(self):
        pass

    def refresh(self):
        pass
