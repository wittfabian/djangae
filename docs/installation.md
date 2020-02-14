# Installation

1. Make sure you have gcloud tools installed, and you've installed the Datastore Emulator
1. For local development, you'll want to pip install `gcloud-tasks-emulator` and `gcloud-storage-emulator` from PyPi
1. Create a Django project, add app.yaml and main.py to the root. Make sure Django 2.2+ is in your project and importable.
1. Add a requirements.txt to the root of your project, add djangae to it and install in your environment
1. Add `'djangae'` to `INSTALLED_APPS`, and probably also `'djangae.tasks'`.  This must come before any `django` apps.
1. We also recommend that you:
    - Add `'djangae.contrib.security'` to `INSTALLED_APPS'`.
    - Add `'djangae.contrib.security.middleware.AppEngineSecurityMiddleware'` to `MIDDLEWARE_CLASSES`.
1. At the top of your `settings.py`, insert the following line to setup some default settings: 

```python
from djangae.settings_base import *
```

In `app.yaml` add the following handlers:

```yml
runtime: python37

handlers:
# This configures Google App Engine to serve the files in the app's static
# directory.
- url: /static
  static_dir: static/

# This handler routes all requests not caught above to your main app. It is
# required when static routes are defined, but can be omitted (along with
# the entire handlers section) when there are no static files defined.
- url: /.*
  script: auto
```

Make your `manage.py` look something like this:

```python
#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapp.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    from djangae.sandbox import start_emulators, stop_emulators

    try:
        # Start all emulators, persisting data if we're not testing
        start_emulators(persist_data="test" not in sys.argv)
        execute_from_command_line(sys.argv)
    finally:
        # Stop all emulators
        stop_emulators()
```

Use the Django WSGI handler in your main.py, something like

```python
from .wsgi import application
app = application
```

It is recommended that for improved security you add `djangae.contrib.security.middleware.AppEngineSecurityMiddleware` as the first of your middleware classes. This middleware patches a number of insecure parts of the Python and App Engine libraries and warns if your Django settings aren't as secure as they could be.

## Deployment

Deploying your application is the same as deploying any Google App Engine project.
