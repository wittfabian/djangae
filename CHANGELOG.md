## v0.9.5 (in progress)

### New features & improvements:

-

### Bug fixes:

- Fix JSONField behaviour in forms: it's properly validating JSON string before saving
it and returns json object, not string when accessed through cleaned_data. 

### Documentation:

-

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
