from django.contrib import admin
from django import forms

# DJANGAE
from djangae.contrib.gauth.datastore.models import (
    GaeDatastoreUser,
    Group
)

class UserAdminForm(forms.ModelForm):
    username = forms.CharField(required=False)

    def clean_username(self):
        return self.cleaned_data['username'] or None

@admin.register(GaeDatastoreUser)
class UserAdmin(admin.ModelAdmin):
    exclude = ('password',)
    form = UserAdminForm

    def save_model(self, request, user, form, change):
        if not user.password:
            user.set_password(None)
        user.save()

admin.site.register(Group)
