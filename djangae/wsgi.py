from djangae.utils import on_production


class DjangaeApplication(object):

    def fix_sandbox(self):
        """
            This is the nastiest thing in the world...

            This WSGI middleware is the first chance we get to hook into anything. On the dev_appserver
            at this point the Python sandbox will have already been initialized. The sandbox replaces stuff
            like the subprocess module, and the select module. As well as disallows _sqlite3. These things
            are really REALLY useful for development.

            So here we dismantle parts of the sandbox. Firstly we add _sqlite3 to the allowed C modules.

            This only happens on the dev_appserver, it would only die on live. Everything is checked so that
            changes are only made if they haven't been made already.
        """

        if on_production():
            return

        from google.appengine.tools.devappserver2.python import sandbox

        if '_sqlite3' not in sandbox._WHITE_LIST_C_MODULES:
            sandbox._WHITE_LIST_C_MODULES.extend([
                '_sqlite3',
                '_ssl', # Workaround for App Engine bug #9246
                '_socket'
            ])

            # Reload the system socket.py, because of bug #9246
            import imp
            import os
            import ast

            psocket = os.path.join(os.path.dirname(ast.__file__), 'socket.py')
            imp.load_source('socket', psocket)

    def __init__(self, application):
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured
        from django import VERSION


        if VERSION[:2] == (1,6):
            for app in settings.INSTALLED_APPS[::-1]:
                if app.startswith("django."):
                    raise ImproperlyConfigured("You must place 'djangae' after 'django' apps in installed apps")
                elif app == "djangae":
                    break
        else:
            for app in settings.INSTALLED_APPS:
                if app.startswith("django."):
                    raise ImproperlyConfigured("In django 1.7 and above, you must place 'djangae' before any 'django' apps in installed apps")
                elif app == "djangae":
                    break

        self.wrapped_app = application

    def __call__(self, environ, start_response):
        self.fix_sandbox()
        return self.wrapped_app(environ, start_response)
