import copy
import functools
import json
import logging
import yaml

from google.appengine.api import urlfetch

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

class ApiSecurityException(Exception):
    """Error when attempting to call an unsafe API."""
    pass


def override_default_kwargs(**overrides):
    """ Wraps a function to set different default values for some/all of the keyword arguments. """
    def decorator(function):
        @functools.wraps(function)
        def replacement(*args, **kwargs):
            # Allow our default kwargs to be overriden if specified
            final_kwargs = copy.deepcopy(overrides)
            final_kwargs.update(**kwargs)
            return function(*args, **final_kwargs)
        return replacement
    return decorator


def check_url_kwarg_for_http(function):
    """ A decorator which checks calls to the given function, and if the `url` kwarg contains a
        string starting with "http://" logs an error.  Function still executes as normal.
    """
    @functools.wraps(function)
    def replacement(*args, **kwargs):
        url = kwargs.get('url')
        if url and url.startswith("http://"):
            logging.warn('SECURITY : fetching non-HTTPS url %s' % url)
        return function(*args, **kwargs)
    return replacement


# JSON.
_JSON_CHARACTER_REPLACEMENT_MAPPING = [
    ('<', '\\u%04x' % ord('<')),
    ('>', '\\u%04x' % ord('>')),
    ('&', '\\u%04x' % ord('&')),
]


class _JsonEncoderForHtml(json.JSONEncoder):
    def encode(self, o):
        chunks = self.iterencode(o, _one_shot=True)
        if not isinstance(chunks, (list, tuple)):
            chunks = list(chunks)
        return ''.join(chunks)

    def iterencode(self, o, _one_shot=False):
        chunks = super(_JsonEncoderForHtml, self).iterencode(o, _one_shot)
        for chunk in chunks:
            for (character, replacement) in _JSON_CHARACTER_REPLACEMENT_MAPPING:
                chunk = chunk.replace(character, replacement)
            yield chunk


PATCHES_APPLIED = False


class AppEngineSecurityMiddleware(object):
    """
        This middleware patches over some more insecure parts of the Python and AppEngine libraries.

        The patches are taken from here: https://github.com/google/gae-secure-scaffold-python

        You should add this middleware first in your middleware classes
    """

    def __init__(self, *args, **kwargs):
        global PATCHES_APPLIED
        if not PATCHES_APPLIED:
            # json module does not escape HTML metacharacters by default.
            use_json_html_encoder = override_default_kwargs(cls=_JsonEncoderForHtml)
            json.dump = use_json_html_encoder(json.dump)
            json.dumps = use_json_html_encoder(json.dumps)

            # YAML.  The Python tag scheme allows arbitrary code execution:
            # yaml.load('!!python/object/apply:os.system ["ls"]')
            use_safe_loader = override_default_kwargs(Loader=yaml.loader.SafeLoader)
            yaml.compose = use_safe_loader(yaml.compose)
            yaml.compose_all = use_safe_loader(yaml.compose_all)
            yaml.load = use_safe_loader(yaml.load)
            yaml.load_all = use_safe_loader(yaml.load_all)
            yaml.parse = use_safe_loader(yaml.parse)
            yaml.scan = use_safe_loader(yaml.scan)

            # AppEngine urlfetch.
            # Does not validate certificates by default.
            validate_cert = override_default_kwargs(validate_certificate=True)
            urlfetch.fetch = validate_cert(urlfetch.fetch)
            urlfetch.make_fetch_call = validate_cert(urlfetch.make_fetch_call)
            urlfetch.fetch = check_url_kwarg_for_http(urlfetch.fetch)
            urlfetch.make_fetch_call = check_url_kwarg_for_http(urlfetch.make_fetch_call)

            for setting in ("CSRF_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SECURE"):
                if not getattr(settings, setting, False):
                    logging.warning("settings.%s is not set to True, this is insecure", setting)

            PATCHES_APPLIED = True
        raise MiddlewareNotUsed()
