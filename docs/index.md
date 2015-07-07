# Djangae

**The best way to run Django on Google App Engine.**

Djangae (jan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you
want to) using Django's models with the App Engine Datastore as the underlying database.

Google Group: [https://groups.google.com/forum/#!forum/djangae-users](https://groups.google.com/forum/#!forum/djangae-users)

Website: [https://potatolondon.github.io/djangae/](https://potatolondon.github.io/djangae/)

GitHub: [https://github.com/potatolondon/djangae](https://github.com/potatolondon/djangae)

**Note: Djangae is under heavy development, stability is not guaranteed. A 1.0 release will happen when it's ready**

## Features

* A WSGI middleware that provides a clean way via which your Django app is plugged into App Engine.
* A hook to allow App Engine's deferred tasks and mapreduce handlers to run through the same environment.
* The ability to use the Datastore as the database for Django's models.  See [The Database Backend](db_backend.md) for details.
  You can also use App Engine's NDB, or you can use Google Cloud SQL (via the standard django MySQL backend) instead of
  or along side the Datastore. Or use all 3!
* [djangae.contrib.gauth](gauth.md) which provides user models (both concrete and extendable abstract versions), an auth backend, and a middleware; which allow you to authenticate users using the App Engine's built-in Google Accounts authentication, and also allow you to use Django's permissions system on the Datastore (i.e. without being caught out by the Many-To-Many relationships).
* A `runserver` command which fires up the App Engine SDK to serve your app (while still using Django's code reloading).
* [The ability to run management commands locally or on the remote App Engine Datastore](sandbox.md).
* A `shell` command that correctly sets up the environment/database. (Note, we should support this set up for any custom commands as well, see [TODO.md](https://github.com/potatolondon/djangae/blob/master/TODO.md)).

## Supported Django Versions

The intention is always to support the last two versions of Django, although older versions may work.

Currently Django 1.6 and 1.7 are supported.

Django 1.8 support is under development.


## Contrib Applications

 - [Authentication with djangae.contrib.gauth](gauth.md)
 - [Map-reduce integration with djangae.contrib.mappers](mappers.md)
 - [Pagination with djangae.contrib.pagination](pagination.md)

