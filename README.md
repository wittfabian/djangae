
# Djangae

Djangae (djan-gee) is a Django app that provides tight integration with the Google App Engine API by sticking as close to vanilla Django usage as possible. The intention is to basically do what djangoappengine has done up to now, but with the following differences:

 * More closely mimic default Django (e.g. make running on App Engine transparent)
 * Implement the whole thing via WSGI middleware
 * Try to avoid importing from internal App Engine code (e.g. dev_appserver.py)
 * Reimplement contrib.auth in a non-rel way rather than trying to make it work

 ## Status

I've only been working on this for a couple of hours, but currently what works is:

 * Environment/path setup - The SDK is detected, sys.path is configured, everything happens in the WSGI middleware
 * Custom runserver command - This wraps dev_appserver to provide a seamless experience, works with Djangos autoreload (something that djangoappengine couldn't manage)

