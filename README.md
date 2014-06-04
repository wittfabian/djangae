
# Djangae

Djangae (djan-gee) is a Django app that provides tight integration with the Google App Engine API by sticking as close to vanilla Django usage as possible.

The intention is to basically do what djangoappengine has done up to now, but with the following differences:

 * More closely mimic default Django (e.g. make running on App Engine transparent)
 * Implement the whole thing via WSGI middleware
 * Try to avoid importing from internal App Engine code (e.g. dev_appserver.py)
 * Reimplement contrib.auth in a non-rel way
 * Integrate query manipulation like dbindexer into the core
 * Integrate elements of djangotoolbox into the core, including a non-user-nullable ListField where NULL fields return [] to workaround the App Engine datastore not storing empty lists
 * Implement caching where it makes sense to work around HRD issues

## Status

 * Environment/path setup - The SDK is detected, sys.path is configured, everything happens in the WSGI middleware
 * Custom runserver command - This wraps dev_appserver to provide a seamless experience, works with Djangos autoreload (something that djangoappengine couldn't manage)
 * Connector is mostly implemented, many contrib tests are passing, also many of django's model tests
 * A seamless replacement for dbindexer is built in, a file called djangaeidx.yaml will be generated automatically when you use __iexact queries or the like


# HOW DO I USE THIS THING?!?!

 * Shove the Djangae folder in the root of your project, either by symlink or directly - or .. whatever
 * Add djangae to INSTALLED_APPS
 * At the top of your settings, insert the following line: `from djangae.settings_base import *` - this sets up some default settings
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
 * Add the following to your URL handler: url(r'^_ah/', include('djangae.urls')),


## TODO

### Bug Fixing

Detect and manipulate queries that use Django model inheritance to just query the base class table as all data is stored there. Don't forget to filter on `class`.

This should fix errors like this one:

    ======================================================================
    ERROR: test_inherited_unique (testapp.django_model_tests.model_forms.tests.UniqueTest)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "/home/lukebens/Potato/Djangae-testapp/testapp/django_model_tests/model_forms/tests.py", line 448, in test_inherited_unique
        self.assertFalse(form.is_valid())
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/forms/forms.py", line 126, in is_valid
        return self.is_bound and not bool(self.errors)
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/forms/forms.py", line 117, in _get_errors
        self.full_clean()
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/forms/forms.py", line 274, in full_clean
        self._post_clean()
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/forms/models.py", line 344, in _post_clean
        self.validate_unique()
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/forms/models.py", line 353, in validate_unique
        self.instance.validate_unique(exclude=exclude)
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/db/models/base.py", line 731, in validate_unique
        errors = self._perform_unique_checks(unique_checks)
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/db/models/base.py", line 826, in _perform_unique_checks
        if qs.exists():
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/db/models/query.py", line 610, in exists
        return self.query.has_results(using=self.db)
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/db/models/sql/query.py", line 447, in has_results
        return bool(compiler.execute_sql(SINGLE))
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/db/models/sql/compiler.py", line 830, in execute_sql
        sql, params = self.as_sql()
      File "/home/lukebens/Potato/Djangae-testapp/djangae/db/backends/appengine/compiler.py", line 47, in as_sql
        validate_query_is_possible(self.query)
      File "/home/lukebens/Potato/Djangae-testapp/djangae/db/backends/appengine/compiler.py", line 40, in validate_query_is_possible
        """ % query.join_map)
    NotSupportedError:
                The appengine database connector does not support JOINs. The requested join map follows

                {(None, u'model_forms_derivedbook', None, None): (u'model_forms_derivedbook',), (u'model_forms_derivedbook', u'model_forms_book', u'book_ptr_id', u'id'): (u'model_forms_book',)}


Note that running `testapp.UniqueTest.test_inherited_unique` on its own passes, but when running the whole test case (specifically when `test_abstract_inherited_unique` and `test_abstract_inherited_unique_together` are run as well) that first test then fails. If you put PDB into django/db/models/base.py circa line 826 in `_perform_unique_checks` then you will see that when the test is run on its own `qs.query.count_active_tables()` returns 1, but when the test is run with the those other 2 tests as well then `qs.query.count_active_tables()` returns 2 and hence the `CouldBeSupported` error is raised.
I think that the error is being correctly raised, but the question is what those other tests are doing which is causing the query to change! It's as if something to do with calling `DerivedBook.objects.create` is causing something to "fix" the tables used in query.
Note that if you call `django.db.backends.mysql.compiler.SQLCompiler(qs, django.db.connection, None).as_sql()` on the query set at that PDB point, then that also triggers the error.  So it's as if those other 2 tests are causing code similar to that (but not actually that) to be run somewhere.


Implement the FK Null Fix from dbindexer (which manipulates the query in the case a join is used for isnull).



The following test also started failing, we need to investigate to find the failing query and fix up Djangae

    ======================================================================
    FAIL: test_formset_instance (django.contrib.formtools.tests.wizard.forms.FormTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "/home/lukebens/Potato/Djangae-testapp/google_appengine/lib/django-1.5/django/contrib/formtools/tests/wizard/forms.py", line 192, in test_formset_instance
        self.assertEqual(instance.get_form().initial_form_count(), 1)
    AssertionError: 0 != 1


Make `MyModel.objects.filter(pk=1) | MyModel.objects.filter(pk=2)` correctly return an empty result.  Currently results in `DataBaseError`.


### djangae.contrib.auth

This is a duplication of django.contrib.auth which we should fix up to remove the ManyToMany fields (using ListFields). We should make the minimal changes, but also add an additional authentication backend that uses App Engine's users API

### Memcache backend

I think we need a memcache backend. Take a look at djappengine on GitHub, perhaps we could just use the one from there. Although I'm not convinced that the standard memcache backend won't work. Needs testing.

### extra() selects

It should be possible to support extra selects, this is not yet implemented and throws a CouldBeSupportedError

### Special Indexing

This is what I've termed the old-style dbindexer magic that allow stuff like iexact to work. How it works in Djangae is when you run a query on the dev_appserver (e.g. `username__iexact="bananas"`), an index is added to djangaeidx.yaml (just like index.yaml). From that point onwards every save of the field should create an associated `_idx_***` field storing a transformed version of the value. Special lookups (like iexact) will then use this field.

Status: 90% - the yaml file is generated during tests (although I haven't implemented the dev_appserver sandbox circumvention yet). iexact is implemented.

### Unique Caching

This is implemented hackily and brokenly. We should follow the same logic as NDB here (with the in-context vs memcache layer) but extend it to unique field values. We also need to make sure we follow the same logic with transactions as they do to ensure they work correctly.

Status: 10% - needs a total rewrite, I have an uncommitted file that started stubbing this out. I just need to get around to doing it

### Cross-kind Selects

We should be able to support a select that bridges a single join, on a single model provided the where does not cross models. For example Permission.objects.values_list("user__username", "id"). We can do this while processing the result set by gathering related keys, doing a single datastore Get(keys) and reading the resulting field value. In the above example, after processing the auth_permission results, we can do a Get for the users, and update the result set. This behaviour should be supported (to allow more of Django to work by default) but should log a warning in the Djangae slow query log (see below).

Status: 0% - needs to be done to make the contrib.auth tests pass

### Slow Query Logging

We should have a special log for when Djangae performs an inefficient query, or if an unsupported ordering is requested. This should be displayed in the terminal when running locally, but not on production. We should log in the following situations:

 - The user does a cross-kind select (see above) - Info
 - The result set needs to be manipulated in Python to fulfil the query (this isn't necessarily slow, but we should be verbose to the user so they can perhaps better structure their query) - Info
 - An unsupported cross-table ordering is requested. Ideally we would raise an exception in this case, but many models in contrib do this and I'd rather tell the user that their ordering did not apply, than throw an exception and make the whole thing unusable - Warning
 - The query was totally unsupported (e.g. ManyToMany, join etc.) - Error

Status: 0% - needs to be done

### Break up django_instance_to_entity

This currently handles transforming field data ready for the datastore, but also converting non-abstract model inheritance to poly models and a bunch of other stuff. We should break this logic up so that can use the same logic for updates as inserts (updates might only use a subset of fields).

Status: 20% - needs to be done, probably needs a whiteboard discussion. I've broken some of this into get_prepared_db_value.

### Fix up deploy, remote, etc. commands

We need to support remote commands, and deployment. Deploy is implemented but I think it needs some tweaking, remote commands are unimplemented

Status: 40%

--- Below this line doesn't stop us using it ---

### Ancestor queries, Expando models etc.

Ancestor queries do exist in our Djangoappengine fork, but the API could do with some improving and it all needs implementing in Djangae. Preferably we could implement this at as high a level as possible.

Status: 0%

### Use Django's Transaction Decorators

I'm not sure how possible this is, we can't advertise supporting transactions (otherwise Django assumes it can roll back an entire table) however, we might be able to support the decorator stuff.

Status: 0%

### Profiling

We need to profile and optimize all parts of the database. My aim is to not only outperform djangoappengine, but also NDB for the same kind of queries. Totally doable (NDB is just a layer on top of Get/Put/Query/MultiQuery the same as djangoappengine and Djangae)

Status: 0%
