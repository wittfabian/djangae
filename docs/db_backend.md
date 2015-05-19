# The Database Backend

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
* A collection of Django model fields which provide useful functionality when using the Datastore.  A `ListField`, `SetField`, `RelatedSetField`, `ShardedCounterField` and `JSONField`.  See the [model fields README](djangae/fields/README.md) for full details.

## Roadmap

1.0-beta

 - Support for ancestor queries. Lots of tests
 - All NotSupportedError tests being skipped, everything passes in the testapp
 - Namespaces handled via the connection settings

## What Can't It Do?

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


## Other Considerations

When using the Datastore you should bear in mind its capabilities and limitations. While Djangae allows you to run
Django on the Datastore, it doesn't turn the Datastore into a relational database. There are things which the
datastore is good at (e.g. handling huge bandwidth of reads and writes) and things which it isn't good at
(e.g. counting). Djangae is not a substitute for knowing how to use the
[Datastore](https://developers.google.com/appengine/docs/python/datastore/).

## Using Other Databases

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

 - `DJANGAE_CACHE_ENABLED` (default `True`). Setting to False it all off, I really wouldn't suggest doing that!
 - `DJANGAE_CACHE_TIMEOUT_SECONDS` (default `60 * 60`). The length of time stuff should be kept in memcache.

## Datastore Behaviours

The Djangae database backend for the Datastore contains some clever optimisations and integrity checks to make working with the Datastore easier.  This means that in some cases there are behaviours which are either not the same as the Django-on-SQL behaviour or not the same as the default Datastore behaviour. So for clarity, below is a list of statements which are true:

* Doing `MyModel.objects.create(primary_key_field=value)` will do an insert, so will explicitly check that an object with that PK doesn't already exist before inserting, and will raise an IntegrityError if it does. This is done in a transaction, so there is no need for any kind of manual transaction or existence checking.

## On Delete Constraints

In general, django's emulation of SQL ON DELETE constraints works with djangae on the datastore. Due to eventual consistency however, the constraints can fail. Take care when deleting related objects in quick succession, a PROTECT constraint can wrongly cause a ProtectedError when deleting an object that references a recently deleted one. Constraints can also fail to raise an error if a referencing object was created just prior to deleting the referenced one. Similarly, when using ON CASCADE DELETE (the default behaviour), a newly created referencing object might not be deleted along with the referenced one.

## Transactions

**Do not use `google.appengine.ext.db.run_in_transaction` and friends, it will break.**

The following functions are available to manage transactions:

 - `djangae.db.transaction.atomic` - Decorator and Context Manager. Starts a new transaction, accepted `xg`, `indepedendent` and `mandatory` args
 - `djangae.db.transaction.non_atomic` - Decorator and Context Manager. Breaks out of any current transactions so you can run queries outside the transaction
 - `djangae.db.transaction.in_atomic_block` - Returns True if inside a transaction, False otherwise