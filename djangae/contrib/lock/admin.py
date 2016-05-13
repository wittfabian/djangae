from django.contrib import admin


from djangae.contrib.lock.models import DatastoreLock


admin.site.register(DatastoreLock)
