## Authentication

Djangae includes 'djangae.contrib.gauth', which allows you to authenticate your users with App Engine's built-in Google Accounts functionality, and also allows use of Django's permissions system on the Datastore, despite it usually requiring many-to-many relationships, which are not supported on the Datstore.

To set up Djangae's authentication system:

* Add `'djangae.contrib.gauth'` to `INSTALLED_APPS` probably after `'django.contrib.auth'`.
* At the bottom of your settings.py add: `from djangae.contrib.gauth.settings import *`.  This sets up the auth backend,
   login url and sets `AUTH_USER_MODEL` to `'djangae.GaeDatastoreUser'`.
* Replace 'django.contrib.auth.middleware.AuthenticationMiddleware' with `'djangae.contrib.gauth.middleware.AuthenticationMiddleware'`.

### Choosing A User Model

There are 4 possible ways in which you may want to set up your authentication and database.  Djangae provides 4 different user models which correspond to these cases:

1. Standard user model on a SQL database.
	* Set `AUTH_USER_MODEL = 'djangae.GaeUser'`.
	* This is equivalent to `django.contrib.auth.models.User`, but works with the Google Accounts authentication.
2. Custom user model on a SQL database.
	* Create your own `User` class by subclassing `djangae.contrib.gauth.models.GaeAbstractUser`.
	* This base model is equivalent to `django.contrib.auth.models.AbstractBaseUser`, but works with the Google Accounts authentication.
3. Standard user model on the Datastore.
	* Set `AUTH_USER_MODEL = 'djangae.GaeDatastoreUser'`.
	* This is equivalent to `django.contrib.auth.models.User`, but works with the Google Accounts authentication, and provides permissions models which work on the non-relational Datastore (i.e. they avoid M2M relationships while providing the same functionality).
4. Custom user model on the Datastore.
	* Create your own `User` class by subclassing `GaeAbstractDatastoreUser`.
	* This base model is equivalent to `django.contrib.auth.models.AbstractBaseUser`, but works with the Google Accounts authentication, and provides permissions models which work on the non-relational Datastore (i.e. they avoid M2M relationships while providing the same functionality).

#### Permissions

If you're using the Datastore for your User model (i.e. case *3.* or *4.* from above) then the permissions work slightly differently.  The Datastore-based user models have a `user_permissions` list field, which takes the place of the usual many-to-many relationship to a `Permission` model.  For groups, Djangae provides `djangae.contrib.gauth.Group`, which again has a list field for storing the permissions.  This `Group` model is registered with the Django admin automatically for you in cases *3.* and *4.* from above.

### User Pre-Creation

When using Google Accounts-based authentication, the `username` field of the user model is populated with the `user_id` which is provided by Google Accounts.  This is populated when the user object is created on the user's first log in, and is then used as the authentication check for subsequent log ins.  It is impossible to know what this ID is going to be before the user logs in, which creates an issue if you want to create users and assign permissions to them before they have authenticated.

Djangae allows you to pre-create users by specifying their email address.  First, you need to set `ALLOW_USER_PRE_CREATION` to `True` in settings, and then you can create user objects which have an email address and a `username` of `None`.  Djangae then recognises these as pre-created users, and will populate the `username` with their Google `user_id` when they first log in.

### Username/password authentication

As well as using Djangae's Google Accounts-based authentication, you can also use the standard authentication backend from django.contrib.auth.  They can work alongside each other.  Simply include both, like this:


```
AUTHENTICATION_BACKENDS = (
    'djangae.contrib.gauth.backends.AppEngineUserAPI',
    'django.contrib.auth.backends.ModelBackend',
)

MIDDLEWARE_CLASSES = (
    'djangae.contrib.gauth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
)
```
