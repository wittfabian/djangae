from django.contrib.auth.models import AbstractUser, Group as OriginalGroup, Permission
from djangae.fields import ListField
from django.db import models
from django.utils.translation import ugettext_lazy as _

class Group(OriginalGroup):
    permissions = ListField(models.ForeignKey(Permission),
        verbose_name=_('permissions'), blank=True)

    def __init__(self, *args, **kwargs):
        super(Group, self)._meta.abstract = True
        super(Group, self).__init__(*args, **kwargs)

class User(AbstractUser):
    groups = ListField(models.ForeignKey(Group), verbose_name=_('groups'),
        blank=True, help_text=_('The groups this user belongs to. A user will '
                                'get all permissions granted to each of '
                                'his/her group.'))
    user_permissions = ListField(models.ForeignKey(Permission),
        verbose_name=_('user permissions'), blank=True,
        help_text='Specific permissions for this user.')