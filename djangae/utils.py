import os
import sys
import time
import logging
from socket import socket, SHUT_RDWR


def application_id():
    from google.appengine.api import app_identity

    try:
        result = app_identity.get_application_id()
    except AttributeError:
        result = None

    if not result:
        # Apparently we aren't running live, probably inside a management command
        from google.appengine.api import appinfo

        info = appinfo.LoadSingleAppInfo(open(os.path.join(find_project_root(), "app.yaml")))

        result = "dev~" + info.application
        os.environ['APPLICATION_ID'] = result
        result = app_identity.get_application_id()

    return result


def appengine_on_path():
    try:
        from google.appengine.api import apiproxy_stub_map
        apiproxy_stub_map  # Silence pylint
        return True
    except ImportError:
        return False


def on_production():
    return 'SERVER_SOFTWARE' in os.environ and not os.environ['SERVER_SOFTWARE'].startswith("Development")


def datastore_available():
    from google.appengine.api import apiproxy_stub_map
    return bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))


def in_testing():
    return "test" in sys.argv


import collections
import functools

class memoized(object):
    def __init__(self, func, *args):
        self.func = func
        self.cache = {}
        self.args = args

    def __call__(self, *args):
        args = self.args or args
        if not isinstance(args, collections.Hashable):
         # uncacheable. a list, for instance.
         # better to not cache than blow up.
         return self.func(*args)

        if args in self.cache:
            return self.cache[args]
        else:
            value = self.func(*args)
            self.cache[args] = value
            return value

    def __repr__(self):
        '''Return the function's docstring.'''
        return self.func.__doc__

    def __get__(self, obj, objtype):
        '''Support instance methods.'''
        return functools.partial(self.__call__, obj)

@memoized
def find_project_root():
    """Traverse the filesystem upwards and return the directory containing app.yaml"""
    path = os.path.dirname(os.path.abspath(__file__))
    app_yaml_path = os.environ.get('DJANGAE_APP_YAML_LOCATION', None)

    # If the DJANGAE_APP_YAML_LOCATION variable is setup, will try to locate
    # it from there.
    if (app_yaml_path is not None and
            os.path.exists(os.path.join(app_yaml_path, "app.yaml"))):
        return app_yaml_path

    # Failing that, iterates over the parent folders until it finds it,
    # failing when it gets to the root
    while True:
        if os.path.exists(os.path.join(path, "app.yaml")):
            return path
        else:
            parent = os.path.dirname(path)
            if parent == path:  # Filesystem root
                break
            else:
                path = parent

    raise RuntimeError("Unable to locate app.yaml. Did you add it to skip_files?")


def get_in_batches(queryset, batch_size=10):
    """ prefetches the queryset in batches """
    start = 0
    if batch_size < 1:
        raise Exception("batch_size must be > 0")
    end = batch_size
    while True:
        batch = [x for x in queryset[start:end]]
        for y in batch:
            yield y
        if len(batch) < batch_size:
            break
        start += batch_size
        end += batch_size


def retry_until_successful(func, *args, **kwargs):
    return retry(func, *args, _retries=float('inf'), **kwargs)


def retry(func, *args, **kwargs):
    from google.appengine.api import datastore_errors
    from google.appengine.runtime import apiproxy_errors
    from google.appengine.runtime import DeadlineExceededError
    from djangae.db.transaction import TransactionFailedError

    retries = kwargs.pop('_retries', 3)
    i = 0
    try:
        timeout_ms = 100
        while True:
            try:
                i += 1
                return func(*args, **kwargs)
            except (datastore_errors.Error, apiproxy_errors.Error, TransactionFailedError), exc:
                logging.info("Retrying function: %s(%s, %s) - %s", str(func), str(args), str(kwargs), str(exc))
                time.sleep(timeout_ms / 1000000.0)
                timeout_ms *= 2
                if i > retries:
                    raise exc

    except DeadlineExceededError:
        logging.error("Timeout while running function: %s(%s, %s)", str(func), str(args), str(kwargs))
        raise


def djangae_webapp(request_handler):
    """ Decorator for wrapping a webapp2.RequestHandler to work with
    the django wsgi hander"""

    def request_handler_wrapper(request, *args, **kwargs):
        from webapp2 import Request, Response, WSGIApplication
        from django.http import HttpResponse

        class Route:
            handler_method = request.method.lower()

        req = Request(request.environ)
        req.route = Route()
        req.route_args = args
        req.route_kwargs = kwargs
        req.app = WSGIApplication()
        response = Response()
        view_func = request_handler(req, response)
        view_func.dispatch()

        django_response = HttpResponse(response.body, status=int(str(response.status).split(" ")[0]))
        for header, value in response.headers.iteritems():
            django_response[header] = value

        return django_response

    return request_handler_wrapper


def port_is_open(port, url):
    s = socket()
    try:
        s.connect((url, int(port)))
        s.shutdown(SHUT_RDWR)
        return True
    except:
        return False


def get_next_available_port(url, port):
    for offset in xrange(10):
        if port_is_open(url, port + offset):
            port = port + offset
            break
    return port
