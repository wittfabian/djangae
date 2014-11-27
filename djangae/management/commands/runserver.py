import os

from django.core.management.commands.runserver import BaseRunserverCommand

from datetime import datetime


class Command(BaseRunserverCommand):
    """
    Overrides the default Django runserver command.

    Instead of starting the default Django development server this
    command fires up a copy of the full fledged App Engine
    dev_appserver that emulates the live environment your application
    will be deployed to.
    """

    def inner_run(self, *args, **options):
        import sys

        shutdown_message = options.get('shutdown_message', '')

        # We use the old dev appserver if threading is disabled or --old was passed
        quit_command = 'CTRL-BREAK' if sys.platform == 'win32' else 'CONTROL-C'

        from djangae.utils import find_project_root
        from djangae.sandbox import _find_sdk_from_python_path

        from django.conf import settings
        from django.utils import translation

        # Check for app.yaml
        expected_path = os.path.join(find_project_root(), "app.yaml")
        if not os.path.exists(expected_path):
            sys.stderr.write("Unable to find app.yaml at '%s'\n" % expected_path)
            sys.exit(1)

        self.stdout.write("Validating models...\n\n")
        self.validate(display_num_errors=True)
        self.stdout.write((
            "%(started_at)s\n"
            "Django version %(version)s, using settings %(settings)r\n"
            "Starting development server at http://%(addr)s:%(port)s/\n"
            "Quit the server with %(quit_command)s.\n"
        ) % {
            "started_at": datetime.now().strftime('%B %d, %Y - %X'),
            "version": self.get_version(),
            "settings": settings.SETTINGS_MODULE,
            "addr": self._raw_ipv6 and '[%s]' % self.addr or self.addr,
            "port": self.port,
            "quit_command": quit_command,
        })
        sys.stdout.write("\n")
        sys.stdout.flush()

        # django.core.management.base forces the locale to en-us. We should
        # set it up correctly for the first request (particularly important
        # in the "--noreload" case).
        translation.activate(settings.LANGUAGE_CODE)

        # Will have been set by setup_paths
        sdk_path = _find_sdk_from_python_path()


        from google.appengine.tools.devappserver2 import devappserver2
        from google.appengine.tools.devappserver2 import api_server
        from google.appengine.tools.devappserver2 import python_runtime
        from djangae import sandbox

        class NoConfigDevServer(devappserver2.DevelopmentServer):
            @staticmethod
            def _create_api_server(request_data, storage_path, options, configuration):
                return api_server.APIServer(options.api_host, options.api_port, configuration.app_id)

        python_runtime._RUNTIME_PATH = os.path.join(sdk_path, '_python_runtime.py')
        python_runtime._RUNTIME_ARGS = [sys.executable, python_runtime._RUNTIME_PATH]
        devappserver = NoConfigDevServer()
        devappserver.start(sandbox._OPTIONS)

        if shutdown_message:
            sys.stdout.write(shutdown_message)

        return
