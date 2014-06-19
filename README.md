
# Djangae

The sexiest way to run Django on Google App Engine.

Djangae (djan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you want to) using Django's models with the App Engine Datastore as the underlying database.

## Features

* A WSGI middleware that provides a clean way via which your Django app is plugged into App Engine.
* A hook to allow App Engine's deferred tasks and mapreduce handlers to run through the same environment.
* The ability to use use the Datastore as the database for Django's models.  See **The Database Backend** for details.  You can also use App Engine's NDB, or you can use Google Cloud SQL (via the standard django MySQL backend) instead of or along side the Datastore.  Or use all 3!
* `djangae.contrib.auth` which provides a custom user model, auth backend and middleware that makes django.contrib.auth work on the datastore (i.e. without Many-To-Many relationships).
* A `runserver` command which fires up the App Engine SDK to serve your app (while still using Django's code reloading).
* A `remote` command to allow any of your management commands to be run on the remote App Engine Datastore.
* A `shell` command that correctly sets up the environment/database. (Note, we should support this set up for any custom commands as well, see TODO.md).


## The Database Backend

Previously, in order to use Django's ORM with the App Engine Datastore, django-nonrel was required, along with djangoappengine.  That's now changed.  With Djangae you can use vanilla Django with the Datastore.  Heavily inspired by djangoappengine (thanks Waldemar!) Djangae provides an intelligent database backend that allows vanilla Django to be used, and makes use of many of the Datastore's speed and efficiency features such as projection queries.

Here's the full list of magic:

* Database-level enforcement of `unique` and `unique_together` constraints.
* A transparent caching layer for queries which return a single result (`.get` or any query filtering on a unique field or unique-together fields). This helps to avoid issues with the [Datastore's eventual consistency behaviour](https://developers.google.com/appengine/docs/python/datastore/structuring_for_strong_consistency_.
* Automatic creation of additional index fields containing pre-manipulated values, so that queries such as `__iexact` work out of the box.  These index fields are created automatically when you use the queries.  Use `settings.GENERATE_SPECIAL_INDEXES_DURING_TESTING` to control whether that automatic creation happens during tests.
* Support for queries which weren't possible with djangoappengine, such as OR queries using `Q` objects.
* A `ListField` which provides a "normal" django model field for storing lists (a feature of the Datastore).


### What Can't It Do?

Due to the limitations of the App Engine Datastore (it being a non-relational database for a start), there are some things which you still can't do with the Django ORM when using the djangae backend.  The easiest way to find these out is to just build your app and look out for the `NotSupportedError` exceptions.  But if you don't like surprises, here's a quick list:

* `ManyToManyField` - a non-relational database simply can't do these (or not efficiently).  However, you can probably solve these kind of problems using djangae's `ListField`.  We may even create a many-to-many replacement based on that in the future.
* `__in` queries with more than 30 values.  This is a limitation of the Datastore.  You can filter for up to 500 values on the primary key field though.
* More than one in equality filter, i.e. you can't do `.exclude(a=1, b=2)`.  This is a limitation of the Datastore.
* Transactions.  The Datastore has transactions, but they are not "normal" transactions in the SQL sense.  Transactions should be done using `google.appengine.api.datastore.RunInTransaction`.


### Other Considerations

When using the Datastore you should bear in mind its capabilities and limitations.  While Djangae allows you to run Django on the Datastore, it doesn't turn the Datastore into a non-relational database.  There are things which the datastore is good at (e.g. handling huge bandwidth of reads and writes) and things which it isn't good at (e.g. counting).  Djangae is not a substitute for knowing [how to use the Datastore](https://developers.google.com/appengine/docs/python/datastore/).


# HOW DO I USE THIS THING?!?!

 * Create up your App Engine project as usual (with app.yaml, etc).
 * Create your django project (with settings.py, wsgi.py, etc and place it inside your App Engine project).
 * Shove the Djangae folder in the root of your project, either by symlink or directly - or .. whatever.
 * Add djangae to `INSTALLED_APPS`.
 * At the top of your settings, insert the following line: `from djangae.settings_base import *` - this sets up some default settings.
 * In app.yaml, add your preferred version of `django` to the `libraries` section, or include the library in your project folder if you'd rather. [Docs](LINK HERE).
 * In app.yaml add the following handlers:

 ```
- url: /_ah/(mapreduce|queue|warmup).*
  script: YOUR_DJANGO_APP.wsgi.application
  login: admin

- url: /.*
  script: YOUR_DJANGO_APP.wsgi.application
 ```

 * You may also want to add `- ^\.gaedata` to the `skip_files` section in app.yaml, as that's where the local development Datastore data is located.
 * Make your manage.py look something like this:

 ```
 if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myapp.settings")

    from djangae.boot import setup_paths
    setup_paths()

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
 ```

 * Use the Djangae WSGI handler in your wsgi.py, something like

 ```
    from django.core.wsgi import get_wsgi_application
    from djangae.wsgi import DjangaeApplication

    application = DjangaeApplication(get_wsgi_application())
 ```
 * Add the following to your URL handler: `url(r'^_ah/', include('djangae.urls'))`


## djangae.contrib.auth

This includes a custom user model, auth backend and middleware that makes django.contrib.auth work on the datastore.

To use, do the following:

 - At the bottom of your settings.py add: from djangae.contrib.auth.settings import * (this sets up the auth backend, login url and custom user model)
 - Replace 'django.contrib.auth.middleware.AuthenticationMiddleware' with 'djangae.contrib.auth.middleware.AuthenticationMiddleware'
 - Add 'djangae.contrib.auth' to INSTALLED_APPS probably after 'django.contrib.auth'


## Using other databases

You can use Google Cloud SQL or sqlite (locally) instead of or along side the Datastore.

Note that the Database backend and settings for the Datastore remain the same whether you're in local development on on App Engine Production, djanagae switches between the SDK and the production datastore appropriately.  However, with Cloud SQL you will need to switch the settings yourself, otherwise you could find yourself developing on your live database!

Here's an example of how your `DATABASES` might look in settings.py if you're using both Cloud SQL and the Datastore.

```
from djangae.boot import on_production

DATABASES = {
		'default': {
            'ENGINE': 'djangae.db.backends.appengine'
        }
}

if on_production():
    DATABASES['sql'] = {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': '/cloudsql/YOUR_GOOGLE_CLOUD_PROJECT:YOUR_INSTANCE_NAME',
        'NAME': 'YOUR_DATABASE_NAME',
        'USER': 'root',
    }
else:
    DATABASES['sql'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'development.sqlite3'
    }
```

See the Google documentation for more information on connecting to Cloud SQL [via the MySQL client](https://developers.google.com/cloud-sql/docs/mysql-client) and [from external applications](https://developers.google.com/cloud-sql/docs/external).
