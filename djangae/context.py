"""Context managers for command-line scripts started outside of dev_appserver/remote_api_shell.
Assumes that the GAE SDK is installed and dev_appserver.py is on the PATH.

Example usage:

    #!/usr/bin/env python

    import os
    import sys

    if __name__ == "__main__":
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gumballsite.settings")

        import djangae.context as context

        with context.local():
            from django.core.management import execute_from_command_line
            execute_from_command_line(sys.argv)

"""
import os
import sys
import contextlib
import subprocess
import getpass

import djangae.utils as utils


def _find_sdk(script_name):
    """Assumes `script_name` is on your PATH - SDK installers set this up"""
    which = 'where' if sys.platform == "win32" else 'which'
    path = subprocess.check_output([which, script_name])
    return os.path.dirname(os.path.realpath(path))


@contextlib.contextmanager
def _nearly_sandbox(ctx_name):
    project_root = utils.find_project_root()
    original_path = sys.path[:]
    original_modules = sys.modules.copy()

    # Setup paths as though we were running dev_appserver. This is similar to
    # what the App Engine script wrappers do.
    script_name = 'dev_appserver.py'
    sdk_path = _find_sdk(script_name)
    sys.path[0:0] = [sdk_path]
    import wrapper_util
    _PATHS = wrapper_util.Paths(sdk_path)
    sys.path = (_PATHS.script_paths(script_name) + _PATHS.scrub_path(script_name, sys.path))

    # Initialize as though `dev_appserver.py` is about to run our app, using all the
    # configuration provided in app.yaml.
    import google.appengine.tools.devappserver2.application_configuration as application_configuration
    import google.appengine.tools.devappserver2.python.sandbox as sandbox
    import google.appengine.tools.devappserver2.devappserver2 as devappserver2
    import google.appengine.tools.devappserver2.wsgi_request_info as wsgi_request_info
    import google.appengine.ext.remote_api.remote_api_stub as remote_api_stub

    # The argparser is the easiest way to get the default options.
    options = devappserver2.PARSER.parse_args([project_root])
    configuration = application_configuration.ApplicationConfiguration(options.config_paths)


    # Take dev_appserver paths off sys.path - our app cannot access these
    sys.path = original_path[:]


    # Enable App Engine libraries without enabling the full sandbox.
    module = configuration.modules[0]
    for l in sandbox._enable_libraries(module.normalized_libraries):
        sys.path.insert(0, l)

    try:
        if ctx_name == 'local':
            devappserver2._setup_environ(configuration.app_id)
            storage_path = devappserver2._get_storage_path(options.storage_path, configuration.app_id)
            dispatcher = None
            request_data = wsgi_request_info.WSGIRequestInfo(dispatcher)

            apis = devappserver2.DevelopmentServer._create_api_server(
                request_data, storage_path, options, configuration)
            apis.start()
            try:
                yield
            finally:
                apis.quit()

        elif ctx_name == 'remote':
            def auth_func():
                return raw_input('Google Account Login: '), getpass.getpass('Password: ')

            if configuration.app_id.startswith('dev~'):
                app_id = configuration.app_id[4:]
            else:
                app_id = configuration.app_id

            remote_api_stub.ConfigureRemoteApi(
                None,
                '/_ah/remote_api',
                auth_func,
                servername='{0}.appspot.com'.format(app_id),
                secure=True,
            )

            ps1 = getattr(sys, 'ps1', None)
            red = "\033[0;31m"
            native = "\033[m"
            sys.ps1 = red + '(remote) ' + app_id + native + ' >>> '

            try:
                yield
            finally:
                sys.ps1 = ps1

        else:
            raise RuntimeError('Unknown context name "{}"'.format(ctx_name))

    finally:
        sys.path = original_path
        sys.modules = original_modules


@contextlib.contextmanager
def local():
    with _nearly_sandbox('local'):
        yield


@contextlib.contextmanager
def remote():
    with _nearly_sandbox('remote'):
        yield
