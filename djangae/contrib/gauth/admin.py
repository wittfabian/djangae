from django.contrib import admin
from django.contrib.auth import get_user_model

from djangae.contrib.auth.models import GaeUser, GaeDatastoreUser

# Only register the user model with the admin if it is a Djangae model.  If a different/custom user
# model is in use, then allow that app to deal with the Django admin.

user_model = get_user_model()
if user_model in (GaeUser, GaeDatastoreUser):
    # Note that we don't need Django's usual custom Admin class with the password change form because
    # users created through the App Engine users API do not have passwords stored in our DB.
    admin.site.register(user_model)
