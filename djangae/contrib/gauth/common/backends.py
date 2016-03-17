import warnings

from django.db.utils import IntegrityError
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

from google.appengine.api import users

# DJANGAE
from djangae.contrib.gauth.common.models import GaeAbstractBaseUser

# Backwards compatibility, remove before 1.0
# This is here so that we only log once on import, not on each authentication
if hasattr(settings, "ALLOW_USER_PRE_CREATION"):
    warnings.warn(
        "settings.ALLOW_USER_PRE_CREATION is deprecated, "
        "please use DJANGAE_CREATE_UNKNOWN_USER instead"
    )

if hasattr(settings, 'DJANGAE_FORCE_USER_PRE_CREATION'):
    warnings.warn(
        'settings.DJANGAE_FORCE_USER_PRE_CREATION is deprecated, please use'
        ' DJANGAE_CREATE_UNKNOWN_USER instead'
    )

if hasattr(settings, 'DJANGAE_ALLOW_USER_PRE_CREATION'):
    warnings.warn(
        'settings.DJANGAE_ALLOW_USER_PRE_CREATION is deprecated, please use'
        ' DJANGAE_CREATE_UNKNOWN_USER instead'
    )


def should_create_unknown_user():
    """Returns True if we should create a Django user for unknown users.

    Default is False.
    """
    if hasattr(settings, 'DJANGAE_CREATE_UNKNOWN_USER'):
        return settings.DJANGAE_CREATE_UNKNOWN_USER

    if hasattr(settings, 'DJANGAE_FORCE_USER_PRE_CREATION'):
        # This setting meant that there _had_ to be an existing user, it would
        # refuse to create a new user (except for admins).
        return not settings.DJANGAE_FORCE_USER_PRE_CREATION

    if hasattr(settings, 'DJANGAE_ALLOW_USER_PRE_CREATION'):
        return settings.DJANGAE_ALLOW_USER_PRE_CREATION

    if hasattr(settings, 'ALLOW_USER_PRE_CREATION'):
        return settings.ALLOW_USER_PRE_CREATION

    return False


class BaseAppEngineUserAPIBackend(ModelBackend):
    atomic = transaction.atomic
    atomic_kwargs = {}

    def authenticate(self, google_user=None):
        """
        Handles authentication of a user from the given credentials.
        Credentials must be a 'google_user' as returned by the App Engine
        Users API.
        """
        if google_user is None:
            return None

        User = get_user_model()

        if not issubclass(User, GaeAbstractBaseUser):
            raise ImproperlyConfigured(
                "AppEngineUserAPIBackend requires AUTH_USER_MODEL to be a "
                " subclass of djangae.contrib.auth.base.GaeAbstractBaseUser."
            )

        user_id = google_user.user_id()
        email = BaseUserManager.normalize_email(google_user.email())

        try:
            # User exists and we can bail immediately.
            return User.objects.get(username=user_id)
        except User.DoesNotExist:
            pass

        auto_create = should_create_unknown_user()
        user_is_admin = users.is_current_user_admin()

        if not (auto_create or user_is_admin):
            # User doesn't exist and we aren't going to create one.
            return None

        # OK. We will grant access. We may need to update an existing user, or
        # create a new one, or both.

        # Those 3 scenarios are:
        # 1. A User object has been created for this user, but that they have not logged in yet.
        # In this case wefetch the User object by email, and then update it with the Google User ID
        # 2. A User object exists for this email address but belonging to a different Google account.
        # This generally only happens when the email address of a Google Apps account has been
        # signed up as a Google account and then the apps account itself has actually become a
        # Google account. This is possible but very unlikely.
        # 3. There is no User object realting to this user whatsoever.

        try:
            existing_user = User.objects.get(email=email)
        except User.DoesNotExist:
            existing_user = None

        if existing_user:
            if existing_user.username is None:
                # We can use the existing user for this new login.
                existing_user.username = user_id
                existing_user.email = email
                existing_user.last_login = timezone.now()
                existing_user.save()

                return existing_user
            else:
                # We need to update the existing user and create a new one.
                with self.atomic(**self.atomic_kwargs):
                    existing_user = User.objects.get(pk=existing_user.pk)
                    existing_user.email = None
                    existing_user.save()

                    return User.objects.create_user(user_id, email=email)
        else:
            # Create a new user, but account for another thread having created it already in a race
            # condition scenario. Our logic cannot be in a transaction, so we have to just catch this.
            try:
                return User.objects.create_user(user_id, email=email)
            except IntegrityError:
                return User.objects.get(username=user_id)
