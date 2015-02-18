from django.contrib import admin

# DJANGAE
from djangae.contrib.gauth.models import (
    GaeUser,
    GaeDatastoreUser,
    Group
)

admin.site.register(GaeUser)
admin.site.register(GaeDatastoreUser)
admin.site.register(Group)
