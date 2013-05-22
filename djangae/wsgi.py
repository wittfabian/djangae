

class DjangaeApplication(object):
    def __init__(self, application):
        self.wrapped_app = application

    def __call__(self, environ, start_response):
        return self.wrapped_app(environ, start_response)
