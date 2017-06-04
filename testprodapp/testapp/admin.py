from django.contrib import admin

from .models import TestResult
from .models import Uuid


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'name',
        'last_modified',
        'status',
        'data',
    )


@admin.register(Uuid)
class UuidAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'value',
    )
