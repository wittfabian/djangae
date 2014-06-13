import os
import sys
import getpass

from django.core.management.base import BaseCommand, OutputWrapper
from django.core.management import execute_from_command_line


class Command(BaseCommand):

    def run_from_argv(self, argv):
        import yaml
        from google.appengine.ext.remote_api import remote_api_stub
        from djangae.boot import find_project_root

        self.stdout = OutputWrapper(sys.stdout)

        def auth_func():
            return raw_input('Google Account Login:'), getpass.getpass('Password:')

        with open(os.path.join(find_project_root(), 'app.yaml')) as f:
            config = yaml.load(f.read())

        app_id = config['application']

        self.stdout.write("Opening Remote API connection to {0}...\n".format(app_id))

        remote_api_stub.ConfigureRemoteApi(
            None,
            '/_ah/remote_api',
            auth_func,
            servername='{0}.appspot.com'.format(app_id),
            secure=True,
        )
        self.stdout.write("...Connection established...have a nice day :)\n".format(app_id))
        argv = argv[:1] + argv[2:]
        execute_from_command_line(argv)
