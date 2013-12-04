
from django.core.management.commands.test import Command as DjangoCommand

class Command(DjangoCommand):
    def __init__(self, *args, **kwargs):
        from djangae.boot import setup_paths, setup_datastore_stubs

        setup_paths()
        setup_datastore_stubs()

        super(Command, self).__init__(*args, **kwargs)

