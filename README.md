# Djangae

[![build-status-image]][travis]

The best way to run Django on Google App Engine.

Djangae (djan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you
want to) using Django's models with the App Engine Datastore as the underlying database.

Documentation: http://djangae.readthedocs.org/

Google Group: https://groups.google.com/forum/#!forum/djangae-users

Website: https://potatolondon.github.io/djangae/

GitHub: https://github.com/potatolondon/djangae

**Note: Djangae is under heavy development, stability is not guaranteed. A 1.0 release will happen when it's ready**

## Features

* A WSGI middleware that provides a clean way via which your Django app is plugged into App Engine.
* A hook to allow App Engine's deferred tasks and mapreduce handlers to run through the same environment.
* The ability to use the Datastore as the database for Django's models.  See **The Database Backend** for details.
  You can also use App Engine's NDB, or you can use Google Cloud SQL (via the standard django MySQL backend) instead of
  or along side the Datastore. Or use all 3!
* `djangae.contrib.gauth` which provides user models (both concrete and extendable abstract versions), an auth backend, and a middleware; which allow you to authenticate users using the App Engine's built-in Google Accounts authentication, and also allow you to use Django's permissions system on the Datastore (i.e. without being caught out by the Many-To-Many relationships).
* A `runserver` command which fires up the App Engine SDK to serve your app (while still using Django's code reloading).
* The ability to run management commands locally or on the remote App Engine Datastore.
* A `shell` command that correctly sets up the environment/database. (Note, we should support this set up for any
  custom commands as well, see TODO.md).

## Documentation

http://djangae.readthedocs.org/

## Supported Django Versions

The intention is always to support the last two versions of Django, although older versions may work. Currently
Django 1.6 and 1.7 are supported. 1.8 support will come soon after it's released.

# Installation

**If you just want to get started on a fresh Django project, take a look at [djangae-scaffold](https://github.com/potatolondon/djangae-scaffold)**

 * Create a Django project, add app.yaml to the root. Make sure Django 1.6+ is in your project and importable
 * Install Djangae into your project, make sure it's importable (you'll likely need to manipulate the path in manage.py and wsgi.py)
 * Add djangae to `INSTALLED_APPS`.
 * At the top of your settings, insert the following line: `from djangae.settings_base import *` - this sets up some
   default settings.
 * In app.yaml add the following handlers:

    ```yml
    - url: /_ah/(mapreduce|queue|warmup).*
      script: YOUR_DJANGO_APP.wsgi.application
      login: admin

    - url: /.*
      script: YOUR_DJANGO_APP.wsgi.application
    ```

 * Make your manage.py look something like this:

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

## Testing

For running the tests, (the first time only) you just need to run:

    $ ./runtests.sh

This will download the App Engine SDK, pip install a bunch of stuff locally, download the Django tests and run them. If you want to run the
tests on a specific Django version, simply do:

    $ DJANGO_VERSION=1.8 ./runtests.sh

Currently the default is 1.6. TravisCI runs on 1.6 and 1.7 currently, and 1.8 in the 1-8-support branch.

After you have run the tests once, you can do:

    $ cd testapp
    ./runtests.sh

This will avoid the re-downloading of the SDK and libraries.  Note that if you want to switch Django version then you need to use the `runtests.sh` command in the parent directory again.

You can run specific tests in the usual way by doing:

    ./runtests.sh some_app.SomeTestCase.some_test_method

## Contributing

Contributions are accepted via pull request and will be reviewed as soon as possible. If you have access to master, please do not commit directly! Pull requests only!

[build-status-image]: https://secure.travis-ci.org/potatolondon/djangae.png?branch=master
[travis]: http://travis-ci.org/potatolondon/djangae?branch=master
