from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

# DJANGAE
from djangae.contrib.gauth.models import GaeAbstractUser


class AppEngineUserAPI(ModelBackend):
    """
        A custom Django authentication backend, which lets us authenticate against the Google
        users API
    """

    supports_anonymous_user = True

    def authenticate(self, **credentials):
        """
        Handles authentication of a user from the given credentials.
        Credentials must be a combination of 'request' and 'google_user'.
         If any other combination of credentials are given then we raise a TypeError, see authenticate() in django.contrib.auth.__init__.py.
        """

        User = get_user_model()

        if not issubclass(User, GaeAbstractUser):
            raise ImproperlyConfigured(
                "djangae.contrib.auth.backends.AppEngineUserAPI requires AUTH_USER_MODEL to be a "
                " subclass of djangae.contrib.auth.models.GaeAbstractUser."
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
                if getattr(settings, 'ALLOW_USER_PRE_CREATION', False):
                    # Check to see if a User object for this email address has been pre-created.
                    try:
                        # Convert the pre-created User object so that the user can now login via
                        # Google Accounts, and ONLY via Google Accounts.
                        user = User.objects.get(email=BaseUserManager.normalize_email(email), username=None)
                        user.username = user_id
                        user.last_login = timezone.now()
                        user.save()
                        return user
                    except User.DoesNotExist:
                        pass
                user = User.objects.create_user(user_id, email)

            return user
        else:
            raise TypeError()  # Django expects to be able to pass in whatever credentials it has, and for you to raise a TypeError if they mean nothing to you
