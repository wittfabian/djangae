
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    load_backend,
    logout,
)

from .backends.oauth import OAuthBackend
from .models import OAuthUserSession


def authentication_middleware(get_response):

    def middleware(request):
        if request.user.is_authenticated():
            backend_str = request.session.get(BACKEND_SESSION_KEY)
            if (not backend_str) or not isinstance(load_backend(backend_str), OAuthBackend):
                # The user is authenticated with Django, and they use the OAuth backend, so they
                # should have a valid oauth session
                oauth_session = OAuthUserSession.objects.filter(
                    email_address=request.user.email
                ).first()

                # If we have an oauth session, but it's not valid, try
                # refreshing it
                if oauth_session and not oauth_session.is_valid():
                    oauth_session.refresh()

                # If we're still not valid, then log out the Django user
                if not oauth_session or not oauth_session.is_valid():
                    logout(request.user)
