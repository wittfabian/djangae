import django.core.management.base as base


class Command(base.BaseCommand):

    def handle(self, *args, **options):
        self.stderr.write(
            'Use dev_appserver.py to run the development server for App Engine apps.\n'
        )
