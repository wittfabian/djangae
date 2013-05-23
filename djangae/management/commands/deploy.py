import os
import signal
import sys
import time
from subprocess import Popen

from django.core.management.base import BaseCommand


class Command(BaseCommand):

    option_list = BaseCommand.option_list
    help = "Deploy your application into Google App Engine"

    def handle(self, *args, **options):
        shutdown_message = options.get('shutdown_message', '')

        from djangae.boot import setup_paths, find_project_root
        setup_paths()

        project_root = find_project_root()

        expected_path = os.path.join(project_root, "app.yaml")
        if not os.path.exists(expected_path):
            sys.stderr.write("Unable to find app.yaml at '%s'\n" % expected_path)
            sys.exit(1)

        # Will have been set by setup_paths
        sdk_path = os.environ['APP_ENGINE_SDK']

        appcfg = os.path.join(sdk_path, "appcfg.py")

        # very simple for now, only runs appcfg.py update .
        # TODO: Add more options and route them to appcfg.py
        command = [
            appcfg,
            "update",
            project_root
        ]

        process = Popen(
            command,
            stdout=sys.__stdout__,
            stderr=sys.__stderr__,
            cwd=project_root
        )

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
