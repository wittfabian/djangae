import functools

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from .credentials import create_oauth2_flow
from .state import generate_state


_DEFAULT_OAUTH_SCOPES = [
    "openid%20profile%20email"
]


def oauth_login_required(function, scopes=None):
    scopes = scopes or getattr(settings, "GOOGLEAUTH_OAUTH_SCOPES", _DEFAULT_OAUTH_SCOPES)

    @functools.wraps(function)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated():
            return function(request, *args, **kwargs)
        else:
            flow = create_oauth2_flow(scopes)

            # Redirect the user to the oauth login
            original_url = "%s://%s%s" % (
                request.scheme(),
                request.META['HTTP_HOST'],
                request.get_full_path()
            )

            flow.redirect_uri = "%s://%s%s" % (
                request.scheme(),
                request.META['HTTP_HOST'],
                reverse("googleauth_oauth2callback")
            )

            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=generate_state(
                    request,
                    redirect_to=original_url
                )
            )

            return HttpResponseRedirect(authorization_url)

    return wrapper
