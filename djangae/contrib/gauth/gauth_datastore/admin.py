from django.contrib import admin

# DJANGAE
from djangae.contrib.gauth.gauth_datastore.models import (
    GaeDatastoreUser,
    Group
)

admin.site.register(GaeDatastoreUser)
admin.site.register(Group)
