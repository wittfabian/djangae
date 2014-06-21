import argparse

import djangae.sandbox as sandbox


def execute_from_command_line(argv=None):
    """Wraps Django's `execute_from_command_line` to initialize a djangae
    sandbox before running a management command.

    Note: The '--sandbox' arg must come first. All other args are forwarded to
          Django as normal.
    """
    parser = argparse.ArgumentParser(prog='manage.py')
    parser.add_argument(
        '--sandbox', default=sandbox.LOCAL, choices=sandbox.SANDBOXES.keys())
    parser.add_argument('args', nargs=argparse.REMAINDER)
    namespace = parser.parse_args(argv[1:])

    django_argv = ['manage.py'] + namespace.args

    with sandbox.activate(namespace.sandbox, add_sdk_to_path=True):
        import django.core.management as django_management  # Now on the path
        django_management.execute_from_command_line(django_argv)

