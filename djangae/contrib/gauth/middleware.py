from django.contrib.auth import authenticate, login, logout, get_user, BACKEND_SESSION_KEY, load_backend
from django.contrib.auth.middleware import AuthenticationMiddleware as DjangoMiddleware
from django.contrib.auth.models import BaseUserManager, AnonymousUser

from djangae.contrib.gauth.backends import AppEngineUserAPI

from google.appengine.api import users


class AuthenticationMiddleware(DjangoMiddleware):
    def process_request(self, request):

        django_user = get_user(request)
        google_user = users.get_current_user()

        if django_user.is_anonymous() and google_user:
            # If there is a google user, but we are anonymous, log in!
            django_user = authenticate(google_user=google_user)
            if django_user:
                login(request, django_user)
        elif not django_user.is_anonymous() and not google_user:
            # If we are logged in with django, but not longer logged in with Google
            # then log out
            logout(request)
            django_user = None
        elif not django_user.is_anonymous() and django_user.username != google_user.user_id():
            # If the Google user changed, we need to log in with the new one
            logout(request)
            django_user = authenticate(google_user=google_user)
            if django_user:
                login(request, django_user)

        request.user = django_user or AnonymousUser()

        backend_str = request.session.get(BACKEND_SESSION_KEY)

        if backend_str and google_user:
            backend = load_backend(backend_str)

            # We only do this next bit if the user was authenticated with the AppEngineUserAPI
            # backend, or one of its subclasses
            if isinstance(backend, AppEngineUserAPI):
                # Now make sure we update is_superuser and is_staff appropriately
                is_superuser = users.is_current_user_admin()
                google_email = BaseUserManager.normalize_email(google_user.email())
                resave = False

                if is_superuser != django_user.is_superuser:
                    django_user.is_superuser = django_user.is_staff = is_superuser
                    resave = True

                # for users which already exist, we want to verify that their email is still correct
                if django_user.email != google_email:
                    django_user.email = google_email
                    resave = True

                if resave:
                    django_user.save()
