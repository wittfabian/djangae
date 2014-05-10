from django.core.management.commands.shell import Command as DjangoCommand
from django.conf import settings

class Command(DjangoCommand):
    
    def __init__(self, *args, **kwargs):
        from djangae.boot import setup_paths, setup_datastore_stubs
        setup_paths()
        super(Command, self).__init__(*args, **kwargs)

    def handle_noargs(self, **options):
        from google.appengine.ext.remote_api import remote_api_stub
        from google.appengine.tools import appengine_rpc
        import getpass

        def auth_func():
            return (raw_input('Google Account Login:'), getpass.getpass('Password:'))

        app_id = settings.APP_ID

        self.stdout.write("Opening Remote API connection to {0}...\n\n".format(app_id))
        
        remote_api_stub.ConfigureRemoteApi(None,
            '/_ah/remote_api', 
            auth_func, 
            servername='chargrizzle-app.appspot.com', 
            secure=True,
        )

        self.stdout.write("...Connection established...have a nice day :)\n\n".format(app_id))

        super(Command, self).handle_noargs(**options)