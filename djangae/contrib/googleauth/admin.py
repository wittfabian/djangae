

from django.contrib import admin

from .models import (
    AppOAuthCredentials,
    Group,
    User,
    UserPermission,
)

admin.site.register(AppOAuthCredentials)
admin.site.register(User)
admin.site.register(Group)
admin.site.register(UserPermission)
