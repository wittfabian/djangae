# Djangae

The best way to run Django on Google App Engine.

Djangae (djan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you
want to) using Django's models with the App Engine Datastore as the underlying database.

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

## Supported Django Versions

The intention is always to support the last two versions of Django, although older versions may work. Currently only
Django 1.6 is supported, but 1.7 support is in the pipeline.

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

## The Database Backend

Previously, in order to use Django's ORM with the App Engine Datastore, django-nonrel was required, along with
djangoappengine. That's now changed. With Djangae you can use vanilla Django with the Datastore. Heavily inspired by
djangoappengine (thanks Waldemar!) Djangae provides an intelligent database backend that allows vanilla Django to be
used, and makes use of many of the Datastore's speed and efficiency features such as projection queries.

Here's the full list of magic:

* Database-level enforcement of `unique` and `unique_together` constraints.
* A transparent caching layer for queries which return a single result (`.get` or any query filtering on a unique field
  or unique-together fields). This helps to avoid Datastore
  [consistency issues](https://developers.google.com/appengine/docs/python/datastore/structuring_for_strong_consistency).
* Automatic creation of additional index fields containing pre-manipulated values, so that queries such as `__iexact`
  work out of the box. These index fields are created automatically when you use the queries.  Use
  `settings.GENERATE_SPECIAL_INDEXES_DURING_TESTING` to control whether that automatic creation happens during tests.
* Support for queries which weren't possible with djangoappengine, such as OR queries using `Q` objects.
* A `ListField` which provides a "normal" django model field for storing lists (a feature of the Datastore).

## Roadmap

1.0-beta

 - Support for ancestor queries. Lots of tests
 - All NotSupportedError tests being skipped, everything passes in the testapp
 - Namespaces handled via the connection settings

### What Can't It Do?

Due to the limitations of the App Engine Datastore (it being a non-relational database for a start), there are some
things which you still can't do with the Django ORM when using the djangae backend.  The easiest way to find these out
is to just build your app and look out for the `NotSupportedError` exceptions.  But if you don't like surprises, here's
a quick list:

* `ManyToManyField` - a non-relational database simply can't do these (or not efficiently).  However, you can probably
  solve these kind of problems using djangae's `ListField`.  We may even create a many-to-many replacement based on
  that in the future.
* `__in` queries with more than 30 values.  This is a limitation of the Datastore.  You can filter for up to 500 values
  on the primary key field though.
* More than one inequality filter, i.e. you can't do `.exclude(a=1, b=2)`.  This is a limitation of the Datastore.
* Transactions.  The Datastore has transactions, but they are not "normal" transactions in the SQL sense. Transactions
  should be done using `djangae.db.transactional.atomic`.


### Other Considerations

When using the Datastore you should bear in mind its capabilities and limitations. While Djangae allows you to run
Django on the Datastore, it doesn't turn the Datastore into a relational database. There are things which the
datastore is good at (e.g. handling huge bandwidth of reads and writes) and things which it isn't good at
(e.g. counting). Djangae is not a substitute for knowing how to use the
[Datastore](https://developers.google.com/appengine/docs/python/datastore/).


## Local/remote management commands

If you set your manage.py up as described above, djangae will allow you to run management commands locally or
remotely, by specifying a `--sandbox`. Eg.

  ```
  ./manage.py --sandbox=local shell   # Starts a shell locally (the default)
  ./manage.py --sandbox=remote shell  # Starts a shell using the remote datastore
  ```

With no arguments, management commands are run locally.


## Using other databases

You can use Google Cloud SQL or sqlite (locally) instead of or along side the Datastore.

Note that the Database backend and settings for the Datastore remain the same whether you're in local development or on
App Engine Production, djangae switches between the SDK and the production datastore appropriately.  However, with
Cloud SQL you will need to switch the settings yourself, otherwise you could find yourself developing on your
live database!

Here's an example of how your `DATABASES` might look in settings.py if you're using both Cloud SQL and the Datastore.

```python
    from djangae.utils import on_production

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

See the Google documentation for more information on connecting to Cloud SQL via the
[MySQL client](https://developers.google.com/cloud-sql/docs/mysql-client) and from
[external applications](https://developers.google.com/cloud-sql/docs/external).

## Unique Constraint Checking

**IMPORTANT: Make sure you read and understand this section before configuring your project**


_tl;dr Constraint checking is costly, you might want to disable it globally using `settings.DJANGAE_DISABLE_CONSTRAINT_CHECKS` and re-enable on a per-model basis_


Djangae by default enforces the unique constraints that you define on your models. It does so by creating so called "unique markers" in the datastore.
Unique constraint checks have the following caveats...

 - Unique constraints drastically increase your datastore writes. Djangae needs to create a marker for each unique constraint on each model, for each instance. This means if you have
   one unique field on your model, and you save() Djangae must do two datastore writes (one for the entity, one for the marker)
 - Unique constraints increase your datastore reads. Each time you save an object, Djangae needs to check for the existence of unique markers.
 - Unique constraints slow down your saves(). See above, each time you write a bunch of stuff needs to happen.
 - Updating instances via the datastore API (NDB, DB, or datastore.Put and friends) will break your unique constraints. Don't do that!
 - Updating instances via the datastore admin will do the same thing, you'll be bypassing the unique marker creation

However, unique markers are very powerful when you need to enforce uniqueness. **They are enabled by default** simply because that's the behaviour that Django expects. If you don't want to
use this functionality, you have the following options:

 1. Don't mark fields as unique, or in the meta unique_together - this only works for your models, contrib models will still use unique markers
 2. Disable unique constraints on a per-model basis via the Djangae meta class (again, only works on the model you specify)

```
    class Djangae:
        disable_constraint_checks = True
```

 3. Disable constraint checking globally via `settings.DJANGAE_DISABLE_CONSTRAINT_CHECKS`

The `disable_constraint_checks` per-model setting overrides the global `DJANGAE_DISABLE_CONSTRAINT_CHECKS` so if you are concerned about speed/cost then you might want to disable globally and
override on a per-model basis by setting `disable_constraint_checks = False` on models that require constraints.

## Datastore Caching

Djangae has a built-in caching layer, similar to the one built into NDB - only better! You shouldn't even notice the caching layer at work, it's fairly complex and to understand the
behaviour you are best reading through the caching tests. But here's a general overview:

 - There are two layers of caching, the context cache and the memcache cache
 - When possible, if you get/save an entity it will be cached by it's primary key value, and it's unique constraint combinations
 - This protects against HRD inconsistencies in many situations, and it happens automagically
 - The caching layer is heavily tied into the transaction.atomic decorator. If you use the db.RunInTransaction stuff you are going to have a hard time, so don't do that!
 - You can disable the caching by using the `disable_cache` context manager/decorator. `disable_cache` takes two boolean parameters, `context` and `memcache` so you can
   configure which caches you want disabled. Be careful though, don't toggle the caching on and off too much or you might get into trouble (I'm sure there's a situation you can
   break it but I haven't figured out what it is)
 - The context cache has a complex stack structure, when you enter a transaction the stack is pushed, and when you leave a transaction it's popped. This is to ensure the cache
   gives you the right results at the right time
 - The context cache is cleared on each request, and it's thread-local
 - The memcache cache is not cleared, it's global across all instances and so is updated only when a consistent Get/Put outside a transaction is made
 - Entities are evicted from memcache if they are updated inside a transaction (to prevent crazy)

The following settings are available to control the caching:

 - DJANGAE_CACHE_ENABLED (default True). Setting to False it all off, I really wouldn't suggest doing that!
 - DJANGAE_CACHE_TIMEOUT_SECONDS (default 60 * 60). The length of time stuff should be kept in memcache.
 
## Datastore Behaviours

The Djangae database backend for the Datastore contains some clever optimisations and integrity checks to make working with the Datastore easier.  This means that in some cases there are behaviours which are either not the same as the Django-on-SQL behaviour or not the same as the default Datastore behaviour. So for clarity, below is a list of statements which are true:

* Doing `MyModel.objects.create(primary_key_field=value)` will do an insert, so will explicitly check that an object with that PK doesn't already exist before inserting, and will raise an IntegrityError if it does. This is done in a transaction, so there is no need for any kind of manual transaction or existence checking.

## On Delete Constraints

In general, django's emulation of SQL ON DELETE constraints works with djangae on the datastore. Due to eventual consistency however, the constraints can fail. Take care when deleting related objects in quick succession, a PROTECT constraint can wrongly cause a ProtectedError when deleting an object that references a recently deleted one. Constraints can also fail to raise an error if a referencing object was created just prior to deleting the referenced one. Similarly, when using ON CASCADE DELETE (the default behaviour), a newly created referencing object might not be deleted along with the referenced one.

## Contrib Applications

 - [Authentication with djangae.contrib.gauth](djangae/contrib/gauth/README.md)
 - [Map-reduce integration with djangae.contrib.mappers](djangae/contrib/mappers/README.md)
 - [Pagination with djangae.contrib.pagination](djangae/contrib/pagination/README.md)

## Contributing

Contributions are accepted via pull request and will be reviewed as soon as possible. If you have access to master, please do not commit directly! Pull requests only!
