import django.core.management as django_management

import djangae.sandbox as sandbox


class ManagementUtility(django_management.ManagementUtility):
    """Adds a global --sandbox argument to Django's management commands"""

    def execute(self):
        parser = django_management.LaxOptionParser()
        parser.add_option(
            "-s", "--sandbox", dest="sandbox", default='local',
            help="asdasd")

        # Consume the --sandbox argument which Django doesn't recognize
        options, args = parser.parse_args()
        self.argv = ['manage.py'] + parser.largs

        with sandbox.activate(options.sandbox, add_sdk_to_path=True):
            super(ManagementUtility, self).execute()

    def main_help_text(self, *args, **kwargs):
        # Eurgh, Django really doesn't support global options like these.
        text = super(ManagementUtility, self).main_help_text(*args, **kwargs)
        text += '\n\nAdditional djangae options:\n'
        text += '    -s, --sandbox   specify a sandbox to activate (default: "local")'
        text += '\n'
        return text


def execute_from_command_line(argv=None):
    utility = ManagementUtility(argv)
    utility.execute()
