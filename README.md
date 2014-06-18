
# Djangae

Djangae (djan-gee) is a Django app that provides tight integration with the Google App Engine API by sticking as close to vanilla Django usage as possible.

The intention is to basically do what djangoappengine has done up to now, but with the following differences:

 * More closely mimic default Django (e.g. make running on App Engine transparent)
 * Implement the whole thing via WSGI middleware
 * Try to avoid importing from internal App Engine code (e.g. dev_appserver.py)
 * Reimplement contrib.auth in a non-rel way
 * Integrate query manipulation like dbindexer into the core
 * Integrate elements of djangotoolbox into the core, including a non-user-nullable ListField where NULL fields return [] to workaround the App Engine datastore not storing empty lists
 * Implement caching where it makes sense to work around HRD issues

## Status

 * Environment/path setup - The SDK is detected, sys.path is configured, everything happens in the WSGI middleware
 * Custom runserver command - This wraps dev_appserver to provide a seamless experience, works with Djangos autoreload (something that djangoappengine couldn't manage)
 * Connector is mostly implemented, many contrib tests are passing, also many of django's model tests
 * A seamless replacement for dbindexer is built in, a file called djangaeidx.yaml will be generated automatically when you use __iexact queries or the like


# HOW DO I USE THIS THING?!?!

 * Shove the Djangae folder in the root of your project, either by symlink or directly - or .. whatever
 * Add djangae to INSTALLED_APPS
 * At the top of your settings, insert the following line: `from djangae.settings_base import *` - this sets up some default settings
 * Make your manage.py look something like this:

 ```
 if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myapp.settings")

    from djangae.boot import setup_paths
    setup_paths()

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
 ```

 * Use the Djangae WSGI handler in your wsgi.py, something like

 ```
    from django.core.wsgi import get_wsgi_application
    from djangae.wsgi import DjangaeApplication

    application = DjangaeApplication(get_wsgi_application())
 ```
 * Add the following to your URL handler: `url(r'^_ah/', include('djangae.urls'))`


## djangae.contrib.auth

This includes a custom user model, auth backend and middleware that makes django.contrib.auth work on the datastore.

To use, do the following:

 - At the bottom of your settings.py add: from djangae.contrib.auth.settings import * (this sets up the auth backend, login url and custom user model)
 - Replace 'django.contrib.auth.middleware.AuthenticationMiddleware' with 'djangae.contrib.auth.middleware.AuthenticationMiddleware'
 - Add 'djangae.contrib.auth' to INSTALLED_APPS probably after 'django.contrib.auth'

