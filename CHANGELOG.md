## v0.9.7 (in development)

### New features & improvements:

- Added support for Django 1.10.
- Changed the querying of `ListField` and `SetField`, which now works similiarly to PostgreSQL ArrayField. `isnull` lookup has been replaced with `isempty`, `exact` with `contains` and `in` with `overlap`. This is a breaking change, so stick to Djangae 0.9.6 or update your code.
- Made a slight efficiency improvement so that `my_queryset.filter(pk__in=other_queryset)` will use `other_queryset.values_list('pk')` rather than fetching the full objects.
- Added clearsessions view.

### Bug fixes:

- Fixed a circular import in djangae.db.utils
- Fixed sandbox problem with non-final django versions in the testapp.

### Documentation:

- Added documentation about querying `ListField` and `SetField`.


## v0.9.6 (release date: 1st August 2016)

### New features & improvements:

- ALLOWED_HOSTS is now set to ("*",) by default as App Engine deals with routing and this prevents
  users being confused when their deployed app returns 400 responses.
- Added version string to `__init__`.
- Added an `--install_deps` flag to the `runtests.sh` script to allow triggering of dependency installation without having to delete the SDK folder.
- Added an `--install_sdk` flag to both the `runtests.sh` script and to the `install_deps.py` script in the bundled 'testapp'.
- The `count()` method on `ShardedCounterField` is deprecated because its function was ambiguous or misleading and was often mistakenly used instead of `value()`. It is replaced with a `shard_count()` method.
- It is now possible to have a per-app djangaeidx.yaml file which can be distributed. The indexes in this file
  are combined in memory with the ones from the project root's djangaeidx.yaml. This means that a user of your app
  will not be required to run queries to generate indexes or manually add them to their project file.
- Made a small performance improvement to avoid checking for changes to djangaeindx.yaml files when on production.

### Bug fixes:

- Fixed a regression that prevented precreated users from logging in when `DJANGAE_CREATE_UNKNOWN_USER` is False.
- Fixed a bug where the IntegrityError for a unique constraint violation could mention the wrong field(s).
- Changed the default value of `DJANGAE_CREATE_UNKNOWN_USER` to `True` to match the original behaviour.
- Fixed a bug where simulate contenttypes was required even on a SQL database
- Fixed a bug where filtering on an empty PK would result in an inequality filter being used
- Fixed a bug where making a projection query on time or datetime fields will return truncated values without microseconds
- Fixed a test which could intermittently fail (`test_ordering_on_sparse_field`).
- Fixed a bug where an empty upload_to argument to FileField would result in a broken "./" folder in Cloud Storage.
- Fixed an issue where pre-created users may not have been able to log in if the email address associated with their Google account differed in case to the email address saved in their pre-created User object.
- Made configuration changes to the bundled 'testapp' to allow the `runserver` command to work.
- Fixed a bug in the `install_deps.py` script in the bundled 'testapp' where it would always re-install the App Engine SDK, even if it already existed.

### Documentation:

- Added documentation for:
    - Creating users for gauth.
    - djangaeidx.yaml.
- Improved documentation for:
    - Installation
    - Transactions
    - JSONField
    - RelatedSetField
    - Running management commands locally and remotely
- Fixed incorrect documentation for:
    - The restrictions on projection queries.
- Removed "experimental" flag from the "namespaces" feature of the Datastore DB backend.

## v0.9.5 (release date: 6th June 2016)

### New features & improvements:

- Added the ability to pre-create users in the Django admin who can then log in via Google Accounts.  (Previously you could only pre-create users via the shell.)
- Added new `assert_login_required` and `assert_login_admin` methods to `djangae.test.TestCase`.
- Improved ordering of `sys.path` so that libraries in the application folder take precedence over libraries that are bundled with the SDK (with some hard-to-avoid exceptions).
- Added `djangae.contrib.locking`, for preventing simultaneous executing of functions or blocks of code.
- Moved and renamed several functions from `djangae.utils` to `djangae.environment`.
- Added new task utility functions: `is_in_task()`, `task_name()`, `task_queue_name()`, `task_retry_count()`.
- Extended runserver's file watcher patching to allow ignoring of directories.
- Add tasks utility functions to djangae.environment.
- Alias DatastorePaginator -> Paginator, and DatastorePage -> Page to be more like Django
- Moved `ContentType` patching to `djangae.contrib.contenttypes`. `DJANGAE_SIMULATE_CONTENTTYPES` setting has been removed, add `djangae.contrib.contenttypes` to `INSTALLED_APPS` instead. `djangae.contrib.contenttypes` needs to be after `django.contrib.contenttypes` in the `INSTALLED_APPS` order.
- Allow customization of which user data is synced in gauth `AuthenticationMiddleware`.
- Allow passing `on_change` callback run when ShardedCounter is changed.

### Bug fixes:

- Fixed `atomic` and `non_atomic` transaction decorators/context managers so that they can be called recursively.
- Fix `JSONField` behaviour in forms: it's properly validating JSON string before saving
it and returns json object, not string when accessed through `cleaned_data`.
- Fixing `ListFormField.clean` to return `[]` instead of `None` for empty values.
- Fix computed field `None` values.
- Made retrieving `blob-key` in `BlobstoreFileUploadHandler` easier by using `content_type_extra`. This removes
ugly hacks from before Django 1.7, and fixes issue with regex in `BlobstoreFileUploadHandler` not recognizing
filenames properly.
- Making auth backend catch race condition when creating a new user.
- Fix for `RelatedIterator` that fails when related iterated fields model is set as string.
- Ensure `MapReduceTask `uses the db returned by the application router(s) unless explicitly passed.
- Fixed bug with `__iexact` indexer where values containing underscores would not be correctly indexed.  (Existing objects will need to be re-saved to be correctly indexed.)
- Allow running Djangae tests with non-stable, non-master version of Django.

### Documentation:

- Added a note about `dumpurls` command in documentation
- Updated contributing documentation

## v0.9.4 (release date: 4th April 2016)

This is our first release bringing support for Django 1.9, and dropping support for 1.7.

If you're still using Django 1.7 in your project:
- Upgrade! 1.7 is no longer supported upstream either and has known security issues
- If you can't upgrade, either pin your requirements on 0.9.3 release, or use the 1-7-stable branch, which may receive small fixes if necessary.

### New features & improvements:

 - Added support for Django 1.9
 - The deletion query code has been rewritten entirely to use `DeleteAsync` and now tries to perform deletions in transactional batches of 25. This should result in improved performance but may introduce subtle changes in behaviour, please keep an eye out for issues. For more details take a look at the extensive comment in the `DeleteCommand` class for all the reasons why this is particularly tricky to get right and keep fast.
 - Refactored unique constrains to make them more robust and reliable, fixing edge cases that could cause duplication of unique values.
 - Refactored `InsertCommand` (related to the unique constrains), performance improvements.
 - The Google auth backend has been updated, and a new setting `DJANGAE_CREATE_UNKNOWN_USER` has been added. This replaces the previous settings `DJANGAE_FORCE_USER_PRE_CREATION` and `DJANGAE_ALLOW_USER_PRE_CREATION`.
  - For new projects, `DJANGAE_CREATE_UNKNOWN_USER` defaults to False, meaning you will have to create user objects in the database with matching email addresses to allow people to access your site. For existing projects, the auth backend will recognise the old auth-related settings.
  - If `DJANGAE_CREATE_UNKNOWN_USER=True` then a Django user object will be created automatically when a user accesses your site (if there is no matching user already).
 - Added support for `keep_parents=True` in concrete model inheritance
 - Added support for filters aside from exact on special lookups like `__month` or `__day`. So things like `datefield__month__gt=X` work now
 - Replaced `ensure_instance_included` with `ensure_instance_consistent`
 - Added `ensure_instances_consistent` for the multiple object case
 - Added option to pass `_target` argument to `defer_iteration` in mappers

### Bug fixes:

 - Fixed a bug when saving forms with a RelatedListField or RelatedSetField (#607)
 - JSONField fixes after removing SubfieldBase dependency - to_python added and default value not converted to string anymore

### Documentation:

 - Improvements to storage documentation
 - Replaced links in docs to use https version


## v0.9.3 (release date: 8th March 2016)

### New features & improvements:
- Added support for namespaces
- Refactored cache
- Added Djangae's `CharField` that limits the length by bytes, not characters.
- Improved exception message when encountering multiple inequality filters or uniqueness validation
- Now allowing to override `google_acl` option when uploading to Google Cloud Storage
- Added `BinaryField`
- Added documentation for storage backends
- Added `DJANGAE_IGNORE_REGEXES` settings that allows to only restart dev server for changes on specific filenames. In default, restart dev server only when a `.py`, `.html` or `.yaml` file changes
- Allow `MapReduceTask` tasks to be run on a specific task queue
- Added `ensure_instance_included` to `djangae.db.consistency`
- `djangae.contrib.gauth` now always add users with their emails lowercased
- Provided limited options for `on_delete` on `RelatedSetField` and `RelatedListField`
- Renamed `AppEngineUserAPI` to `AppEngineUserAPIBackend`

### Bug fixes:
- Special indexing now works on fields that are primary keys too
- Fixed a bug with special indexing of datetime fields, that now allows for `__year` or `__month` lookups
- Allow serializing queries containing non-ascii characters
- Don't parse floats as decimals, fixing a bug that causes them to be returned as strings after multiple saves
- `.distinct(x).values_list(x)` no longer cause an error due to the same column being projected twice
- Don't die in `allow_mode_write` if the tempfile module is unavailable
- Fix problems with querying on related fields
- Fixed bug when using `RelatedListField` on a form
- Don't allow ordering by a `TextField`
- Properly limiting number of results when excludes are used
