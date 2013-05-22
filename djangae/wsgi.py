from .boot import setup_paths, on_production

class DjangaeApplication(object):
    @staticmethod
    def fix_sandbox():
        if on_production():
            return

        setup_paths()

        from google.appengine.tools.devappserver2.python import sandbox

        if '_sqlite3' not in sandbox._WHITE_LIST_C_MODULES:
            sandbox._WHITE_LIST_C_MODULES.extend([
                '_sqlite3'
            ])

    def __init__(self, application):
        setup_paths()
        self.wrapped_app = application

    def __call__(self, environ, start_response):
        return self.wrapped_app(environ, start_response)
