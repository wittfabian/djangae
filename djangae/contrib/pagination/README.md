
# Easy Efficient Pagination for the Datastore

Pagination on the datastore is *slow*. This is for a couple of reasons:

 - Counting on the datastore is slow; traditional pagination counts the dataset
 - Skipping results on the datastore is slow; if you slice a query, App Engine literally skips the entities up to the lower bound

# So, what does this app do?

This app provides two things that work together to efficiently paginate datasets on the datastore:

 - @paginated_model - A class decorator that dynamically generates precalculated fields on a model
 - DatastorePaginator - A Paginator subclass which uses the precalculated along with memcache to efficiently paginate and doesn't count all the results

# Wait, doesn't the datastore have cursors?

Yes! However from the docs:

```
Because the != and IN operators are implemented with multiple queries, queries that use them do not support cursors.
```

That's a hell of an annoying caveat. That's not to say our approach doesn't suffer it's own caveats (below), but our approach
will generate an unsupported query, which is obvious to detect, and supports IN and != queries.

# Caveats

Because our pre-calculated fields are indexed, the combined length of the values (plus the unique ID and joining characters) you are
ordering on must not exceed 500 characters. This will throw an error, and if that happens, you'll either need to use a slower paginator (e.g. Django's)
or rethink your design.
