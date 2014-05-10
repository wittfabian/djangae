from django.core.management.commands.shell import Command as DjangoCommand
from django.conf import settings

import os

class Command(DjangoCommand):
    
    def __init__(self, *args, **kwargs):
        from djangae.boot import setup_paths, setup_datastore_stubs
        setup_paths()
        super(Command, self).__init__(*args, **kwargs)

    def handle_noargs(self, **options):
        from google.appengine.ext.remote_api import remote_api_stub
        from google.appengine.tools import appengine_rpc
        import getpass
        from djangae.boot import find_project_root

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

        super(Command, self).handle_noargs(**options)