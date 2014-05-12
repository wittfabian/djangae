# from django.core.management.commands.shell import Command as DjangoCommand
from django.core.management.base import BaseCommand, OutputWrapper
from django.core.management import execute_from_command_line
from django.conf import settings

import os, sys

class Command(BaseCommand):

    def __init__(self, *args, **kwargs):
        from djangae.boot import setup_paths, setup_datastore_stubs
        setup_paths()
        super(Command, self).__init__(*args, **kwargs)

    def run_from_argv(self, argv):
        from google.appengine.ext.remote_api import remote_api_stub
        from google.appengine.tools import appengine_rpc
        import getpass
        from djangae.boot import find_project_root

        self.stdout = OutputWrapper(sys.stdout)

        def auth_func():
            return (raw_input('Google Account Login:'), getpass.getpass('Password:'))

        app_yaml = open(os.path.join(find_project_root(), 'app.yaml')).read()

        app_id = app_yaml.split("application:")[1].lstrip().split()[0]

        self.stdout.write("Opening Remote API connection to {0}...\n".format(app_id))
        remote_api_stub.ConfigureRemoteApi(None,
            '/_ah/remote_api',
            auth_func,
            servername='{0}.appspot.com'.format(app_id),
            secure=True,
        )
        self.stdout.write("...Connection established...have a nice day :)\n".format(app_id))
        argv = argv[:1] + argv[2:]
        execute_from_command_line(argv)
