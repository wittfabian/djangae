# Local/remote management commands

If you set your manage.py up as described [in Installation](installation.md), Djangae will allow you to run management commands locally or
remotely, by specifying a `--sandbox`. Eg.


    ./manage.py --sandbox=local shell   # Starts a shell locally (the default)
    ./manage.py --sandbox=remote shell  # Starts a shell using the remote datastore


With no arguments, management commands are run locally.