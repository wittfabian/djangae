import os
import sys
import time

from django.core.management.commands.runserver import BaseRunserverCommand

from subprocess import Popen
import signal
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
        shutdown_message = options.get('shutdown_message', '')
        quit_command = 'CTRL-BREAK' if sys.platform == 'win32' else 'CONTROL-C'

        from djangae.boot import setup_paths, find_project_root
        setup_paths()

        from django.conf import settings
        from django.utils import translation

        #Check for app.yaml
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

        #Will have been set by setup_paths
        sdk_path = os.environ['APP_ENGINE_SDK']

        dev_appserver = os.path.join(sdk_path, "dev_appserver.py")

        command = [
            dev_appserver,
            find_project_root(),
            "--port",
            self.port,
            "--admin_port",
            "8001"
        ]

        time.sleep(1)

        process = Popen(
            command,
            stdout=sys.__stdout__,
            stderr=sys.__stderr__
        )

        #This makes sure that dev_appserver gets killed on reload
        import atexit
        atexit.register(process.kill)

        try:
            process.wait()
        except KeyboardInterrupt:
            #Tell the dev appserver to shutdown and forcibly kill
            #if it takes too long
            process.send_signal(signal.SIGTERM)
            time.sleep(2)
            process.kill()

            if shutdown_message:
                sys.stdout.write(shutdown_message)

        sys.exit(process.returncode)


