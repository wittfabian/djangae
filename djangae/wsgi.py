from .boot import setup_paths

class DjangaeApplication(object):
    @staticmethod
    def fix_sandbox():
        setup_paths()

        from google.appengine.tools.devappserver2.python import sandbox

        sandbox._WHITE_LIST_C_MODULES.extend([
            '_sqlite3'
        ])


    def __init__(self, application):
        setup_paths()
        self.wrapped_app = application

    def __call__(self, environ, start_response):
        return self.wrapped_app(environ, start_response)
