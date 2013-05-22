from .boot import setup_paths

class DjangaeApplication(object):
    def __init__(self, application):
        setup_paths()

        self.wrapped_app = application

    def __call__(self, environ, start_response):
        return self.wrapped_app(environ, start_response)
