from django.core.urlresolvers import reverse
from django.utils.encoding import iri_to_uri
from google.appengine.api import users


def get_login_url(request=None, next="/"):
    """ Get the URL for logging the user in with Google Accounts, bringing them back to either the
        current URL or a different one, if specified.
    """
    if request:
        next = request.get_full_path()
    return users.create_login_url(next)


def get_logout_url(request=None, next="/"):
    if request:
        next = request.get_full_path()
    return users.create_logout_url(next)


def get_logout_to_login_screen_url(request=None, next="/"):
    """ Get the URL to log the user out and then take them to the Google login page (rather than
        back to this site).  `next` is the path they will come back to if they log in again.
    """
    if request:
        next = request.get_full_path()
    login_url = iri_to_uri(users.create_login_url(next))
    return get_logout_url(next=login_url)


def get_switch_accounts_url(request=None, next="/"):
    """ Get the URL for allowing the user to switch which of their many Google accounts they are
        logged in with.
    """
    if request:
        next = request.get_full_path()
    return reverse("djangae_switch_accounts") + "?next=" + iri_to_uri(next)
