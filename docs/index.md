# Djangae

**The best way to run Django on Google App Engine.**

Djangae (djan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you
want to) using Django's models with the App Engine Datastore as the underlying database.

Google Group: [https://groups.google.com/forum/#!forum/djangae-users](https://groups.google.com/forum/#!forum/djangae-users)

Website: [https://potatolondon.github.io/djangae/](https://potatolondon.github.io/djangae/)

GitHub: [https://github.com/potatolondon/djangae](https://github.com/potatolondon/djangae)

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
* A `shell` command that correctly sets up the environment/database. (Note, we should support this set up for any custom commands as well, see TODO.md).

## Supported Django Versions

The intention is always to support the last two versions of Django, although older versions may work. 

Currently Django 1.6 and 1.7 are supported. 

Django 1.8 support is under development.





## Local/remote management commands

If you set your manage.py up as described above, djangae will allow you to run management commands locally or
remotely, by specifying a `--sandbox`. Eg.

  ```
  ./manage.py --sandbox=local shell   # Starts a shell locally (the default)
  ./manage.py --sandbox=remote shell  # Starts a shell using the remote datastore
  ```

With no arguments, management commands are run locally.


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

## Contrib Applications

 - [Authentication with djangae.contrib.gauth](djangae/contrib/gauth/README.md)
 - [Map-reduce integration with djangae.contrib.mappers](djangae/contrib/mappers/README.md)
 - [Pagination with djangae.contrib.pagination](djangae/contrib/pagination/README.md)

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
