# Installation

**If you just want to get started on a fresh Django project, take a look at [djangae-scaffold](https://github.com/potatolondon/djangae-scaffold)**

 1. Create a Django project, add app.yaml to the root. Make sure Django 1.6+ is in your project and importable
 
 2. Install Djangae into your project, make sure it's importable (you'll likely need to manipulate the path in manage.py and wsgi.py)
 
 3. Add djangae to `INSTALLED_APPS`.
 
 4. At the top of your `settings.py`, insert the following line to setup some default settings: 

```python
from djangae.settings_base import *
```

 5. In `app.yaml` add the following handlers:

```yml
* url: /_ah/(mapreduce|queue|warmup).*
  script: YOUR_DJANGO_APP.wsgi.application
  login: admin

* url: /.*
  script: YOUR_DJANGO_APP.wsgi.application
```

6. Make your `manage.py` look something like this:

```python
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myapp.settings")

    from djangae.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

 * Use the Djangae WSGI handler in your wsgi.py, something like

```python
from django.core.wsgi import get_wsgi_application

from djangae.wsgi import DjangaeApplication

application = DjangaeApplication(get_wsgi_application())
```

 * Add the following to your URL handler: `url(r'^_ah/', include('djangae.urls'))`

 * It is recommended that for improved security you add `djangae.contrib.security.middleware.AppEngineSecurityMiddleware` as the first
   of your middleware classes. This middleware patches a number of insecure parts of the Python and App Engine libraries and warns if your
   Django settings aren't as secure as they could be.
 * If you wish to use the App Engine's Google Accounts-based authentication to authenticate your users, and/or you wish to use Django's permissions system with the Datastore as you DB, then see the section on **Authentication**.
 * **It is highly recommended that you read the section on [Unique Constraints](#unique-constraint-checking)**

## Deployment

Create a Google App Engine project. Edit `app.yaml` and change `application: [...]` to `application: your-app-id`. Then run:

    $ appcfg.py update ./

If you have two-factor authentication enabled in your Google account, run:

    $ appcfg.py --oauth2 update ./