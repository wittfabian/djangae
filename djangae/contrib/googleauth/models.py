from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from gcloudc.db.models.fields.iterable import SetField

from .permissions import get_permission_choices


class User(AbstractUser):
    pass


class UserPermission(models.Model):
    user = models.ForeignKey(User)
    permission = models.CharField(max_length=150, choices=get_permission_choices())  # Format app_label.codename
    obj_id = models.PostiveIntegerField()


class Group(models.Model):
    name = models.CharField(_('name'), max_length=150, unique=True)
    permissions = SetField(
        models.CharField(max_length=150, choices=get_permission_choices()),
        blank=True
    )

    def __str__(self):
        return self.name
