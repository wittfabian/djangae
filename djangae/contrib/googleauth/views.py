from django.http import HttpResponseRedirect

from .credentials import create_oauth2_flow
from .models import OAuthUserSession, _OAUTH_USER_SESSION_SESSION_KEY
from .state import check_state
from django.http import Http404


def oauth2callback(request):
    if request.user.is_authenticated():
        raise Http404(
            "For some reason we hit the oauth2callback even though"
            " we're authenticated"
        )

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
