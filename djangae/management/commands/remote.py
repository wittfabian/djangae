
from django.core.management import call_command
from django.core.management.base import BaseCommand
import subprocess


class Command(BaseCommand):
    help = 'Call a command on the remote instance'

    def add_arguments(self, parser):
        parser.add_argument('subcommand', type=unicode)
        parser.add_argument('--project', type=unicode, required=True)

    def handle(self, *args, **options):
        from google.appengine.ext.remote_api import remote_api_stub

        subprocess.check_call(
            ["gcloud", "auth", "application-default", "login"]
        )

        remote_api_stub.ConfigureRemoteApiForOAuth(
            '{}.appspot.com'.format(options.pop('project')),
            '/_ah/remote_api'
        )

        call_command(options.pop('subcommand'), *args, **options)
