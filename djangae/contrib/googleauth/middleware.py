
from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    _get_user_session_key,
    constant_time_compare,
    load_backend,
    logout,
)

from .backends.iap import IAPBackend
from .backends.oauth import OAuthBackend
from .models import OAuthUserSession


def get_user_object(request):
    """
    Return the user model instance associated with the given request session.
    If no user is retrieved, return an instance of `AnonymousUser`.
    """
    from .models import AnonymousUser

    user = None
    try:
        user_id = _get_user_session_key(request)
        backend_path = request.session[BACKEND_SESSION_KEY]
    except KeyError:
        pass
    else:
        if backend_path in settings.AUTHENTICATION_BACKENDS:
            backend = load_backend(backend_path)
            user = backend.get_user(user_id)
            # Verify the session
            if hasattr(user, 'get_session_auth_hash'):
                session_hash = request.session.get(HASH_SESSION_KEY)
                session_hash_verified = session_hash and constant_time_compare(
                    session_hash,
                    user.get_session_auth_hash()
                )
                if not session_hash_verified:
                    request.session.flush()
                    user = None

    return user or AnonymousUser()


def get_user(request):
    if not hasattr(request, '_cached_user'):
        request._cached_user = get_user_object(request)
    return request._cached_user


def authentication_middleware(get_response):

    def middleware(request):
        # This is taken from the Django auth middleware, just so that
        # users don't have to confusingly install both

        assert hasattr(request, 'session'), (
            "The djangae.contrib.googleauth middleware requires session middleware "
            "to be installed. Edit your MIDDLEWARE setting to insert "
            "'django.contrib.sessions.middleware.SessionMiddleware' before "
            "'django.contrib.auth.middleware.AuthenticationMiddleware'."
        )

        request.user = get_user(request)

        if request.user.is_authenticated:
            backend_str = request.session.get(BACKEND_SESSION_KEY)
            if backend_str and isinstance(load_backend(backend_str), OAuthBackend):
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
            elif backend_str and isinstance(load_backend(backend_str), IAPBackend):
                # FIXME: Implement this
                pass

    return middleware


AuthenticationMiddleware = authentication_middleware
