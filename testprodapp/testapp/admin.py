from django.contrib import admin

from django.conf.urls import patterns
from django.conf.urls import url

from django.shortcuts import redirect

from .models import TestResult
from .models import Uuid
from .prod_tests.entity_counting_test import test_entity_count_vs_length


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'name',
        'last_modified',
        'status',
        'data',
    )

    def get_urls(self):
        urls = super(TestResultAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^count_test/$', self.bulk_create_view, name='test_counting'),
        )
        return my_urls + urls

    def bulk_create_view(self, request):
        test_entity_count_vs_length(create=False)
        return redirect('admin:testapp_testresult_changelist')


@admin.register(Uuid)
class UuidAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'value',
    )

    def get_urls(self):
        urls = super(UuidAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^create/$', self.bulk_create_view, name='bulk_create'),
        )
        return my_urls + urls

    def bulk_create_view(self, request):
        Uuid.objects.create_entities()
        return redirect('admin:testapp_uuid_changelist')
