import logging
from itertools import chain
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

# DJANGAE
from djangae.contrib.gauth.common.models import GaeAbstractBaseUser
from djangae.contrib.gauth.datastore.permissions import get_permission_choices
from djangae.contrib.gauth.common.backends import BaseAppEngineUserAPIBackend


# This is here so that we only log once on import, not on each authentication
if hasattr(settings, "ALLOW_USER_PRE_CREATION"):
    logging.warning("settings.ALLOW_USER_PRE_CREATION is deprecated, please use DJANGAE_ALLOW_USER_PRECREATION instead")


class AppEngineUserAPIBackend(BaseAppEngineUserAPIBackend):
    def get_group_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings that this user has through his/her
        groups.
        """
        if user_obj.is_anonymous() or obj is not None:
            return set()
        if not hasattr(user_obj, '_group_perm_cache'):
            if user_obj.is_superuser:
                perms = (perm for perm, name in get_permission_choices())
            else:
                perms = chain.from_iterable((group.permissions for group in user_obj.groups.all()))
            user_obj._group_perm_cache = set(perms)
        return user_obj._group_perm_cache

    def get_all_permissions(self, user_obj, obj=None):
        if user_obj.is_anonymous() or obj is not None:
            return set()
        if not hasattr(user_obj, '_perm_cache'):
            user_obj._perm_cache = set(user_obj.user_permissions)
            user_obj._perm_cache.update(self.get_group_permissions(user_obj))
        return user_obj._perm_cache

