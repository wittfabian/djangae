
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
 * Connector is mostly implemented, many contrib tests are passing
 * Unique-field caching layer is implemented, but transactions will currently break it, I'll fix this up once the contrib tests pass.


## TODO

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

Status: 0% - needs to be done, probably needs a whiteboard discussion

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
