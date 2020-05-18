# contrib.googleauth

This app gives an authentication system very similar to the built-in contrib.auth that comes with Django. The differences
are as follows:

 - Provides backends for Google Cloud authentication systems
 - Built for the Google Cloud Datastore rather than SQL
 - Permissions are not stored in the database, but are instead generated from apps + models. This avoids M2M relationships
   that wouldn't work well on the Datastore, but sacrifices the ability to create Permissions dynamically.


# Custom Permissions

By default the generated permissions are the standard add, change, delete, and view permissions that Django's auth system
defines. However you can add additional permissions to this on a per-app-model basis or globally by using the `GOOGLEAUTH_CUSTOM_PERMISSIONS`
setting in your settings.py

```
GOOGLEAUTH_CUSTOM_PERMISSIONS = {
    '__all__': ['archive'],
    'events.Event': ['invite']
}
```

# OAuth 2.0 / OpenID Authentication

To enable oauth2 authentication, you'll need to add the following to your `AUTHENTICATION_BACKENDS` setting:

```
AUTHENTICATION_BACKENDS = [
  'djangae.contrib.googleauth.backends.oauth.OAuthBackend'
]
```

Then, add djangae.contrib.googleauth.urls to your url patterns.

After first launch, you should go to the Django admin and fill out your client_id and client_secret settings
in the `AppOAuthCredentials` instance that should've been created for you.
