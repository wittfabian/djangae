import os

from django.core.management.commands.runserver import BaseRunserverCommand

from datetime import datetime

from google.appengine.tools.devappserver2 import shutdown
from google.appengine.tools.sdk_update_checker import (
    GetVersionObject,
    _VersionList
)


class Command(BaseRunserverCommand):
    """
    Overrides the default Django runserver command.

    Instead of starting the default Django development server this
    command fires up a copy of the full fledged App Engine
    dev_appserver that emulates the live environment your application
    will be deployed to.
    """
    def run(self, *args, **options):
        self.use_reloader = options.get("use_reloader")
        options["use_reloader"] = False
        return super(Command, self).run(*args, **options)

    def inner_run(self, *args, **options):
        import sys

        shutdown_message = options.get('shutdown_message', '')

        quit_command = 'CTRL-BREAK' if sys.platform == 'win32' else 'CONTROL-C'

        from djangae.utils import find_project_root
        from djangae.sandbox import _find_sdk_from_python_path
        from djangae.blobstore_service import stop_blobstore_service

        from django.conf import settings
        from django.utils import translation

        stop_blobstore_service()

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
        from google.appengine.tools.devappserver2 import python_runtime

        from djangae import sandbox

        if int(self.port) != sandbox._OPTIONS.port:
            # Override the port numbers
            sandbox._OPTIONS.port = int(self.port)
            sandbox._OPTIONS.admin_port = int(self.port) + 1
            sandbox._OPTIONS.api_port = int(self.port) + 2

        if self.addr != sandbox._OPTIONS.host:
            sandbox._OPTIONS.host = sandbox._OPTIONS.admin_host = sandbox._OPTIONS.api_host = self.addr

        # External port is a new flag introduced in 1.9.19
        current_version = _VersionList(GetVersionObject()['release'])
        if current_version >= _VersionList('1.9.19'):
            sandbox._OPTIONS.external_port = None

        sandbox._OPTIONS.automatic_restart = self.use_reloader

        if sandbox._OPTIONS.host == "127.0.0.1" and os.environ["HTTP_HOST"].startswith("localhost"):
            hostname = "localhost"
        else:
            hostname = sandbox._OPTIONS.host

        os.environ["HTTP_HOST"] = "%s:%s" % (hostname, sandbox._OPTIONS.port)
        os.environ['SERVER_NAME'] = os.environ['HTTP_HOST'].split(':', 1)[0]
        os.environ['SERVER_PORT'] = os.environ['HTTP_HOST'].split(':', 1)[1]
        os.environ['DEFAULT_VERSION_HOSTNAME'] = '%s:%s' % (os.environ['SERVER_NAME'], os.environ['SERVER_PORT'])

        class NoConfigDevServer(devappserver2.DevelopmentServer):
            def _create_api_server(self, request_data, storage_path, options, configuration):
                self._dispatcher = sandbox._create_dispatcher(configuration, options)
                self._dispatcher._port = options.port
                self._dispatcher._host = options.host

                self._dispatcher.request_data = request_data
                request_data._dispatcher = self._dispatcher

                sandbox._API_SERVER._host = options.api_host
                sandbox._API_SERVER.bind_addr = (options.api_host, options.api_port)

                from google.appengine.api import apiproxy_stub_map
                task_queue = apiproxy_stub_map.apiproxy.GetStub('taskqueue')
                # Make sure task running is enabled (it's disabled in the sandbox by default)
                if not task_queue._auto_task_running:
                    task_queue._auto_task_running = True
                    task_queue.StartBackgroundExecution()

                return sandbox._API_SERVER

        python_runtime._RUNTIME_PATH = os.path.join(sdk_path, '_python_runtime.py')
        python_runtime._RUNTIME_ARGS = [sys.executable, python_runtime._RUNTIME_PATH]

        dev_server = NoConfigDevServer()

        try:
            dev_server.start(sandbox._OPTIONS)
            try:
                shutdown.wait_until_shutdown()
            except KeyboardInterrupt:
                pass
        finally:
            dev_server.stop()


        if shutdown_message:
            sys.stdout.write(shutdown_message)

        return
