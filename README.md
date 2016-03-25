# Djangae

[![Join the chat at https://gitter.im/potatolondon/djangae](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/potatolondon/djangae?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

[![build-status-image]][travis] [![codecov.io](https://img.shields.io/codecov/c/github/potatolondon/djangae/master.svg)](http://codecov.io/github/potatolondon/djangae?branch=master)

[![Issue Stats](http://issuestats.com/github/potatolondon/djangae/badge/pr)](http://issuestats.com/github/potatolondon/djangae) [![Issue Stats](http://issuestats.com/github/potatolondon/djangae/badge/issue)](http://issuestats.com/github/potatolondon/djangae)

The best way to run Django on Google App Engine.

Djangae (djan-gee) is a Django app that allows you to run Django applications on Google App Engine, including (if you
want to) using Django's models with the App Engine Datastore as the underlying database.

Documentation: https://djangae.readthedocs.org/

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

https://djangae.readthedocs.org/

## Supported Django Versions

The intention is always to support the last two versions of Django, although older versions may work. Currently
Django 1.8 and 1.9 are supported.

** 1.6 and 1.7 are no longer supported by Djangae, as their not supported by Django either! **

# Installation

See https://djangae.readthedocs.org/en/latest/installation/


## Testing

For running the tests, you just need to run:

    $ ./runtests.sh

On the first run this will download the App Engine SDK, pip install a bunch of stuff locally (into a folder, no virtualenv needed), download the Django tests and run them. If you want to run the tests on a specific Django version, simply do:

    $ DJANGO_VERSION=1.8 ./runtests.sh

Currently the default is 1.8. TravisCI runs on 1.8 and 1.9 currently.

You can run specific tests in the usual way by doing:

    ./runtests.sh some_app.SomeTestCase.some_test_method


## Contributing

Contributions are accepted via pull request and will be reviewed as soon as possible. If you have access to master, please do not commit directly! Pull requests only!

Code style should follow PEP-8 with a loose line length of 100 characters (don't make the code ugly).

[build-status-image]: https://secure.travis-ci.org/potatolondon/djangae.png?branch=master
[travis]: https://travis-ci.org/potatolondon/djangae?branch=master
