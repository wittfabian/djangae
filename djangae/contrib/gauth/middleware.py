from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user, BACKEND_SESSION_KEY, load_backend
from django.contrib.auth.middleware import AuthenticationMiddleware as DjangoMiddleware
from django.contrib.auth.models import BaseUserManager, AnonymousUser
from djangae.contrib.gauth.common.backends import BaseAppEngineUserAPIBackend

from google.appengine.api import users


class AuthenticationMiddleware(DjangoMiddleware):
    def process_request(self, request):
        django_user = get_user(request)
        google_user = users.get_current_user()

        # Check to see if the user is authenticated with a different backend, if so, just set
        # request.user and bail
        if django_user.is_authenticated():
            backend_str = request.session.get(BACKEND_SESSION_KEY)
            if (not backend_str) or not isinstance(load_backend(backend_str), BaseAppEngineUserAPIBackend):
                request.user = django_user
                return

        if django_user.is_anonymous() and google_user:
            # If there is a google user, but we are anonymous, log in!
            # Note that if DJANGAE_CREATE_UNKNOWN_USER=False then this may not authenticate
            django_user = authenticate(google_user=google_user) or AnonymousUser()
            if django_user.is_authenticated():
                login(request, django_user)

        if django_user.is_authenticated():
            if not google_user:
                # If we are logged in with django, but not longer logged in with Google
                # then log out
                logout(request)
                django_user = AnonymousUser()
            elif django_user.username != google_user.user_id():
                # If the Google user changed, we need to log in with the new one
                logout(request)
                django_user = authenticate(google_user=google_user) or AnonymousUser()
                if django_user.is_authenticated():
                    login(request, django_user)

        # Note that the logic above may have logged us out, hence new `if` statement
        if django_user.is_authenticated():
            # Now make sure we update is_superuser and is_staff appropriately
            resave = False

            resave = sync_superuser(django_user)

            # for users which already exist, we want to verify that their email is still correct
            # users are already authenticated with their user_id, so we can save their real email
            # not the lowercased version
            if django_user.email != google_user.email():
                django_user.email = google_user.email()
                resave = True

            if resave:
                django_user.save()

        request.user = django_user


def sync_superuser(user):
    """ Syncs the is_superuser and is_staff flags on the given user with the result of
        is_current_user_admin() according to the DJANGAE_SUPERUSER_SYNC_MODE.
        Returns True if the user needs re-saving.
    """
    mode = getattr(settings, 'DJANGAE_SUPERUSER_SYNC_MODE', 1)
    if mode == 0:
        # Mode 0 is do nothing
        return False
    elif mode == 1:
        # Mode 1 is to make GAE admins superusers, but not require superusers to be GAE admins
        if not (user.is_superuser and user.is_staff) and users.is_current_user_admin():
            user.is_staff, user.is_superuser = True, True
            return True
    elif mode == 2:
        # Mode 2 is to enforce that all superusers are GAE admins and vice versa
        is_gae_admin = users.is_current_user_admin()
        if user.is_superuser != is_gae_admin:
            # You could argue that we shouldn't set is_staff to False if it's currently True, but
            # setting it to False is the safer option
            user.is_superuser = user.is_staff = is_gae_admin
            return True
    return False
