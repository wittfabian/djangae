import logging
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
    logging.warning(
        "settings.ALLOW_USER_PRE_CREATION is deprecated, "
        "please use DJANGAE_ALLOW_USER_PRE_CREATION instead"
    )


class BaseAppEngineUserAPIBackend(ModelBackend):
    """
        A custom Django authentication backend, which lets us authenticate against the Google
        users API
    """
    atomic = transaction.atomic
    atomic_kwargs = {}
    supports_anonymous_user = True

    def authenticate(self, google_user):
        """
        Handles authentication of a user from the given credentials.
        Credentials must be a 'google_user' as returned by the App Engine
        Users API.
        """

        User = get_user_model()

        if not issubclass(User, GaeAbstractBaseUser):
            raise ImproperlyConfigured(
                "djangae.contrib.auth.backends.AppEngineUserAPI requires AUTH_USER_MODEL to be a "
                " subclass of djangae.contrib.auth.base.GaeAbstractBaseUser."
            )

        if google_user is None:
            # users.get_current_user() can return None.
            return None

        user_id = google_user.user_id()
        email = BaseUserManager.normalize_email(google_user.email())
        try:
            return User.objects.get(username=user_id)
        except User.DoesNotExist:
            try:
                existing_user = User.objects.get(email=BaseUserManager.normalize_email(email))
            except User.DoesNotExist:
                force_pre_creation = getattr(settings, 'DJANGAE_FORCE_USER_PRE_CREATION', False)
                user_is_admin = users.is_current_user_admin()
                if force_pre_creation and not user_is_admin:
                    # Indicate to Django that this user is not allowed
                    return
                return User.objects.create_user(user_id, email)

            # If the existing user was precreated, update and reuse it
            if existing_user.username is None:
                if (
                    getattr(settings, 'DJANGAE_ALLOW_USER_PRE_CREATION', False) or
                    # Backwards compatibility, remove before 1.0
                    getattr(settings, 'ALLOW_USER_PRE_CREATION', False)
                ):
                    # Convert the pre-created User object so that the user can now login via
                    # Google Accounts, and ONLY via Google Accounts.
                    existing_user.username = user_id
                    existing_user.last_login = timezone.now()
                    existing_user.save()
                    return existing_user

                # There's a precreated user but user precreation is disabled
                # This will fail with an integrity error
                from django.db import IntegrityError
                raise IntegrityError(
                    "GAUTH: Found existing User with email=%s and username=None, "
                    "but user precreation is disabled." % email
                )

            # There is an existing user with this email address, but it is tied to a different
            # Google user id.  As we treat the user id as the primary identifier, not the email
            # address, we leave the existing user in place and blank its email address (as the
            # email field is unique), then create a new user with the new user id.
            else:
                logging.info(
                    "GAUTH: Creating a new user with an existing email address "
                    "(User(email=%r, pk=%r))", email, existing_user.pk)
                )
                with self.atomic(**self.atomic_kwargs):
                    existing_user = User.objects.get(pk=existing_user.pk)
                    existing_user.email = None
                    existing_user.save()
                    return User.objects.create_user(user_id, email)
