# Local/remote management commands

If you set your manage.py up as described [in Installation](installation.md), Djangae will allow you to run management commands locally or remotely.

## Running Commands Locally

Django management commands run as normal, e.g.


    ./manage.py shell


## Running Commands Remotely

Djangae also lets you run management commands which connect remotely to the Datastore of your deployed App Engine application.  To do this you need to:

Add the `remote_api` built-in to app.yaml, and deploy that change.

    builtins:
      - remote_api: on

You also need to ensure that the `application` in app.yaml is set to the application which you wish to connect to.

Then run your management command specifying the `remote` sandbox.  Note that the `--sandbox` argument needs to come before the name of the management command, e.g.:

    ./manage.py --sandbox=remote shell


This will use your **local** Python code, but all database operations will be performed on the remote Datastore.

### Deferring Tasks Remotely

App Engine tasks are stored in the Datastore, so when you are in the remote shell any tasks that you defer will run on the live application, not locally.  For example:

    ./manage.py --sandbox=remote shell
    >>> from my_code import my_function
    >>> from google.appengine.ext.deferred import defer
    >>> defer(my_function, arg1, arg2, _queue="queue_name")



