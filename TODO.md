
# TODO

Contributions welcome, please get stuck in!


### Bug Fixing

* Unique constraints need to support the `unique_for_date` magic that Django does
* Implement a means to perform ancestor queries through the ORM. Need to think about the API
* Implement an API/Mixin/Custom Field for "expando" models - needs some thought


### Cross-kind Selects

We should be able to support a select that bridges a single join, on a single model provided the where does not cross
models. For example Permission.objects.values_list("user__username", "id"). We can do this while processing the result
set by gathering related keys, doing a single datastore Get(keys) and reading the resulting field value. In the above
example, after processing the auth_permission results, we can do a Get for the users, and update the result set. This
behaviour should be supported (to allow more of Django to work by default) but should log a warning in the Djangae slow
query log (see below).

Status: 0% - needs to be done to make the contrib.auth tests pass


### Ancestor queries, Expando models etc.

Ancestor queries do exist in our Djangoappengine fork, but the API could do with some improving and it all needs
implementing in Djangae. Preferably we could implement this at as high a level as possible.

Status: 0%


### Profiling

We need to profile and optimize all parts of the database. My aim is to not only outperform djangoappengine, but also
NDB for the same kind of queries. Totally doable (NDB is just a layer on top of Get/Put/Query/MultiQuery the same as
djangoappengine and Djangae)

Status: 0%
