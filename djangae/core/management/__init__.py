import sys
import argparse

import djangae.sandbox as sandbox


def _execute_from_command_line(sandbox_name, argv):
    with sandbox.activate(sandbox_name, add_sdk_to_path=True):
        import django.core.management as django_management  # Now on the path
        return django_management.execute_from_command_line(argv)


def execute_from_command_line(argv=None):
    """Wraps Django's `execute_from_command_line` to initialize a djangae
    sandbox before running a management command.

    Note: The '--sandbox' arg must come first. All other args are forwarded to
          Django as normal.
    """
    argv = argv or sys.argv
    parser = argparse.ArgumentParser(prog='manage.py')
    parser.add_argument(
        '--sandbox', default=sandbox.LOCAL, choices=sandbox.SANDBOXES.keys())
    parser.add_argument('args', nargs=argparse.REMAINDER)
    namespace = parser.parse_args(argv[1:])
    return _execute_from_command_line(namespace.sandbox, ['manage.py'] + namespace.args)


def remote_execute_from_command_line(argv=None):
    """Execute commands in the remote sandbox"""
    return _execute_from_command_line(sandbox.REMOTE, argv or sys.argv)


def local_execute_from_command_line(argv=None):
    """Execute commands in the local sandbox"""
    return _execute_from_command_line(sandbox.LOCAL, argv or sys.argv)


def test_execute_from_command_line(argv=None):
    """Execute commands in the test sandbox"""
    return _execute_from_command_line(sandbox.TEST, argv or sys.argv)
