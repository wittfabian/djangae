import logging
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

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

    def authenticate(self, **credentials):
        """
        Handles authentication of a user from the given credentials.
        Credentials must be a combination of 'request' and 'google_user'.
        If any other combination of credentials are given then we raise a TypeError, see
        authenticate() in django.contrib.auth.__init__.py.
        """

        User = get_user_model()

        if not issubclass(User, GaeAbstractBaseUser):
            raise ImproperlyConfigured(
                "djangae.contrib.auth.backends.AppEngineUserAPI requires AUTH_USER_MODEL to be a "
                " subclass of djangae.contrib.auth.base.GaeAbstractBaseUser."
            )

        if len(credentials) != 1:
            # Django expects a TypeError if this backend cannot handle the given credentials
            raise TypeError()

        google_user = credentials.get('google_user', None)

        if google_user:
            user_id = google_user.user_id()
            email = google_user.email().lower()
            try:
                user = User.objects.get(username=user_id)

            except User.DoesNotExist:
                try:
                    old_user = User.objects.get(email=BaseUserManager.normalize_email(email))
                except User.DoesNotExist:
                    return User.objects.create_user(user_id, email)

                # If the existing user was precreated, update and reuse it
                if old_user.username is None:
                    if (
                        getattr(settings, 'DJANGAE_ALLOW_USER_PRE_CREATION', False) or
                        # Backwards compatibility, remove before 1.0
                        getattr(settings, 'ALLOW_USER_PRE_CREATION', False)
                    ):
                        # Convert the pre-created User object so that the user can now login via
                        # Google Accounts, and ONLY via Google Accounts.
                        old_user.username = user_id
                        old_user.last_login = timezone.now()
                        old_user.save()
                        return old_user

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
                        "(User(email=%s, pk=%s))" % (email, old_user.pk)
                    )
                    with self.atomic(**self.atomic_kwargs):
                        old_user = User.objects.get(pk=old_user.pk)
                        old_user.email = None
                        old_user.save()
                        return User.objects.create_user(user_id, email)

            return user
        else:
            raise TypeError()  # Django expects to be able to pass in whatever credentials it has, and for you to raise a TypeError if they mean nothing to you
