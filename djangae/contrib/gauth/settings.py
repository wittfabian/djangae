
AUTHENTICATION_BACKENDS = (
    'djangae.contrib.gauth.datastore.backends.AppEngineUserAPIBackend',
)

AUTH_USER_MODEL = 'djangae.GaeDatastoreUser'
LOGIN_URL = 'djangae_login_redirect'

# Set this to True to allow unknown Google users to sign in. Matching is done
# by email. Defaults to False.
# DJANGAE_CREATE_UNKNOWN_USER = False

# This determines whether/how the gauth middleware updates the `is_superuser` and `is_staff` fields
# based on whether the current user is an admin of the App Engine application
# 0: Do not update the is_superuser or is_staff fields at all.
# 1: Set all App Engine admins to be superusers, but also allow other superusers to exist.
# 2: Set all App Engine admins to be superusers and all non-App Engine admins to not be superusers.
# Default:
# DJANGAE_SUPERUSER_SYNC_MODE = 1
