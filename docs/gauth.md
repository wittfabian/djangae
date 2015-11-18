# Gauth

Djangae includes two applications to aid authentication and user management with
App Engine. Each provides both an abstract class, to extend if you're defining your own custom User model, or a concrete version to use in place of `'django.contrib.auth.models.User'`.  Also provided are custom authentication backends which delegate to the App Engine users API and a middleware to handle the link between the Django's user object and App Engine's (amongst other things).


## Using the Datastore

Allows the use of Django's permissions system on the Datastore, despite it usually requiring many-to-many relationships, which are not supported on the Datastore.

### Setup

1. Add `'djangae.contrib.gauth.datastore'` to `INSTALLED_APPS` probably
after `'django.contrib.auth'`.
2. Replace `'django.contrib.auth.middleware.AuthenticationMiddleware'` with
`'djangae.contrib.gauth.middleware.AuthenticationMiddleware'`.
3. Set `AUTH_USER_MODEL = 'djangae.GaeDatastoreUser'` in your settings file to use the supplied user model, or create your own by subclassing `'djangae.contrib.gauth.datastore.models.AbstractBaseUser'`.
4. Add the backend to `AUTHENTICATION_BACKENDS` in your settings file eg:

```python
AUTHENTICATION_BACKENDS = (
	'djangae.contrib.gauth.datastore.backends.AppEngineUserAPIBackend',
	 ...
)
```

### Permissions

The Datastore-based user models have a `user_permissions` list field, which takes the place of the usual many-to-many relationship to a `Permission` model.  For groups, Djangae provides `djangae.contrib.gauth.Group`, which again has a list field for storing the permissions.  This `Group` model is registered with the Django admin automatically for you.


## Using a relational database (CloudSQL)


### Setup

1. Add `'djangae.contrib.gauth.sql'` to `INSTALLED_APPS` probably
after `'django.contrib.auth'`.
2. Replace `'django.contrib.auth.middleware.AuthenticationMiddleware'` with
`'djangae.contrib.gauth.middleware.AuthenticationMiddleware'`.
3. Set `AUTH_USER_MODEL = 'djangae.GaeUser'` in your settings file to use the supplied user model or create your own by subclassing `'djangae.contrib.gauth.sql.models.AbstractBaseUser'`.
4. Add the backend to `AUTHENTICATION_BACKENDS` in your settings file eg:

```python
AUTHENTICATION_BACKENDS = (
	'djangae.contrib.gauth.sql.backends.AppEngineUserAPIBackend',
	 ...
)
```


## Using your own permissions system

If you want to write your own permissions system, but you still want to take advantage of the authentication provided by the Google Users API, then you may want to subclass `djangae.contrib.gauth.common.models.GaeAbstractBaseUser`.



## User Pre-Creation

When using Google Accounts-based authentication, the `username` field of the user model is populated with the `user_id` which is provided by Google Accounts.  This is populated when the user object is created on the user's first log in, and is then used as the authentication check for subsequent log ins.  It is impossible to know what this ID is going to be before the user logs in, which creates an issue if you want to create users and assign permissions to them before they have authenticated.

Djangae allows you to pre-create users by specifying their email address.  First, you need to set `DJANGAE_ALLOW_USER_PRE_CREATION` to `True` in settings, and then you can create user objects which have an email address and a `username` of `None`.  Djangae then recognises these as pre-created users, and will populate the `username` with their Google `user_id` when they first log in.

## Force user Pre-Creation

If you want to prevent creating users for every single Google Account visiting your website, you can allow only pre-created users to be allowed to log in. To enable that you need to set `DJANGAE_FORCE_USER_PRE_CREATION` to `True` in your settings file.

Note: you don't need to pre-create User for GAE user admins.

## Username/password authentication

As well as using Djangae's Google Accounts-based authentication, you can also use the standard authentication backend from django.contrib.auth.  They can work alongside each other.  Simply include both, like this:

```python
AUTHENTICATION_BACKENDS = (
    'djangae.contrib.gauth.datastore.backends.AppEngineUserAPI',
    'django.contrib.auth.backends.ModelBackend',
)

MIDDLEWARE_CLASSES = (
    'djangae.contrib.gauth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
)
```

## Switching accounts

There is a `switch_accounts` view which allows a user to change which of their Google accounts they're logged in with.

The URL for the user to be sent to afterwards should be provided in `request.GET['next']``.

Learn more about [Google multiple sign-in on App Engine here](https://p.ota.to/blog/2014/2/google-multiple-sign-in-on-app-engine/).

### Example usage:

Include GAuth urls in your main urls.py file.

```python
url(r'^gauth/', include(djangae.contrib.gauth.urls))
```

Use this URL to add "Switch account" functionality for user:

```html
<a href="{% url 'djangae_switch_accounts' %}">Switch account</a>
```
