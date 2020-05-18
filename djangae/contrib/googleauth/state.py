"""
    Functions for encoding/decoding the state parameter sent
    to the oauth login URI
"""

import os
import hashlib
from urllib.parse import quote, urlencode, unquote, parse_qs

_OAUTH_SECURITY_TOKEN_KEY = "_OAUTH_SECURITY_TOKEN"


def generate_state(request, **kwargs):
    token = hashlib.sha256(os.urandom(1024)).hexdigest()

    request.session[_OAUTH_SECURITY_TOKEN_KEY] = token
    request.session.save()

    state = {
        "security_token": token,
    }

    state.update(kwargs)

    # We urlencode to get a traditional querystring from the mapping
    # and then quote that result so that it doesn't interfere with the
    # URL it's appended to. We do the reverse on the way back
    return quote(urlencode(state))


def check_state(request, state):
    state = parse_qs(unquote(state))

    token = state.get("security_token")

    if not token:
        return False, None

    if token != request.session.get(_OAUTH_SECURITY_TOKEN_KEY):
        return False, None

    del request.session[_OAUTH_SECURITY_TOKEN_KEY]

    return True, state
