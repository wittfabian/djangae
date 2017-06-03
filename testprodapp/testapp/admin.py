from django.contrib import admin
from .models import TestResult


class TestResultAdmin(admin.ModelAdmin):
    pass


admin.site.register(TestResult, TestResultAdmin)
