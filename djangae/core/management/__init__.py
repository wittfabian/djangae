import django.core.management as django_management

import djangae.context as context


class ManagementUtility(django_management.ManagementUtility):
    """Adds a global --context argument to Django's management commands"""

    def execute(self):
        parser = django_management.LaxOptionParser()
        parser.add_option("-s", "--context", dest="context", default='local')

        # Consume the --context argument which Django doesn't recognize
        options, args = parser.parse_args()
        self.argv = ['manage.py'] + parser.largs

        contexts = dict(
            local=context.local,
            test=context.test,
            remote=context.remote,
        )
        ctx = contexts[options.context]
        with ctx():
            super(ManagementUtility, self).execute()


def execute_from_command_line(argv=None):
    utility = ManagementUtility(argv)
    utility.execute()
