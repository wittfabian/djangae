# 3RD PARTY
from django import template

# DJANGAE
from djangae.contrib.gauth.utils import (
    get_login_url,
    get_logout_url,
    get_logout_to_login_screen_url,
    get_switch_accounts_url,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def login_url(context, next=None):
    """ Template tag for getting the login URL.  This is an external URL on google.com with
        the continue=xx parameter, etc and so a normal {% url name_here %} doesn't work.
    """
    # only provide the request if `next` is not specified
    request = None if next else context['request']
    return get_login_url(request, next)


@register.simple_tag(takes_context=True)
def logout_url(context, next=None):
    """ Template tag for getting the logout URL.  The destination defaults to the current URL. """
    # only provide the request if `next` is not specified
    request = None if next else context['request']
    return get_logout_url(request, next)


@register.simple_tag(takes_context=True)
def switch_accounts_url(context, next=None):
    """ Template tag for getting the switch_account URL.
        The destination defaults to the current URL.
    """
    # only provide the request if `next` is not specified
    request = None if next else context['request']
    return get_switch_accounts_url(request, next)


@register.simple_tag(takes_context=True)
def logout_to_login_screen_url(context, next=None):
    """ Template tag for getting the URL to logout and then be taken to the login screen (rather
        than back to the site). The destination is the desintaion if they log in again, which
        defaults to the current URL.
    """
    # only provide the request if `next` is not specified
    request = None if next else context['request']
    return get_logout_to_login_screen_url(request, next)
