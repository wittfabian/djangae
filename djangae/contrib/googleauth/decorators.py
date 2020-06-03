import functools

from django.http import HttpResponseRedirect
from django.urls import (
    reverse,
)


def oauth_scopes_required(function, scopes):
    @functools.wraps(function)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated():
            return function(request, *args, **kwargs)
        else:
            # Redirect to the oauth login view (which will then redirect to the oauth flow)
            return HttpResponseRedirect(
                reverse("oauth_login_trigger") + "?next=%s" % (
                    request.get_full_path()
                )
            )

    return wrapper
