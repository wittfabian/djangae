from django.conf import settings
from django.http import (
    Http404,
    HttpResponseRedirect,
)
from django.urls import reverse

from .credentials import create_oauth2_flow
from .models import (
    _OAUTH_USER_SESSION_SESSION_KEY,
    OAuthUserSession,
)
from .state import (
    check_state,
    generate_state,
)

_DEFAULT_OAUTH_SCOPES = [
    "openid",
    "profile",
    "email"
]

_DEFAULT_WHITELISTED_SCOPES = _DEFAULT_OAUTH_SCOPES[:]


def login(request):
    """
        This view should be set as your login_url for using OAuth
        authentication. It will trigger the main oauth flow.
    """
    WHITELISTED_SCOPES = getattr(settings, "GOOGLE_OAUTH_SCOPE_WHITELIST", _DEFAULT_WHITELISTED_SCOPES)
    DEFAULT_SCOPES = getattr(settings, "GOOGLEAUTH_OAUTH_SCOPES", _DEFAULT_OAUTH_SCOPES)

    destination = request.GET.get("next", "/")
    scopes = request.GET.get("scopes", "").split("%20")
    scopes = [x for x in scopes if x]

    # This is a security check to make sure we only ask for access
    # to scopes that we've whitelisted. Just in-case the querystring
    # parameter has been manipulated maliciously in some way
    if not all(x in WHITELISTED_SCOPES for x in scopes):
        raise Http404(
            "Not all scopes were whitelisted for the application."
        )

    # If no scopes were provided, then we revert to the default
    # scopes
    scopes = scopes or DEFAULT_SCOPES

    flow = create_oauth2_flow(scopes)

    # Redirect the user to the oauth login
    original_url = "%s://%s%s" % (
        request.scheme(),
        request.META['HTTP_HOST'],
        destination
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


def oauth2callback(request):
    state = request.GET.get("state")
    if not state:
        raise Http404("State is required for security token checking")

    ok, state = check_state(state)

    if not ok:
        raise Http404("Failed security_token check")

    code = request.GET.get("code")
    if not code:
        # FIXME: Surely something nicer than this?
        # configurable failure page or whatever
        raise Http404()

    scopes = request.GET.get("scopes", "").split("%20") or None

    flow = create_oauth2_flow(scopes=scopes)
    flow.fetch_token(authorization_response=code)

    # FIXME: Pass params to oauth session
    oauth_session = OAuthUserSession.objects.create()
    request.session[_OAUTH_USER_SESSION_SESSION_KEY] = oauth_session.pk

    return HttpResponseRedirect(state["redirect_to"])
