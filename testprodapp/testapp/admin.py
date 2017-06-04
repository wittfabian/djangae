from django.contrib import admin

from .models import TestResult
from .models import Uuid


class TestResultAdmin(admin.ModelAdmin):
    pass


admin.site.register(TestResult, TestResultAdmin)


class UuidAdmin(admin.ModelAdmin):
    pass


admin.site.register(Uuid, UuidAdmin)
