from django.contrib import admin
from django.http import Http404
from django.shortcuts import redirect
from django.conf.urls import url
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required

from .models import TestResult
from .prod_tests.entity_counting_test import test_entity_count_vs_length


class TestResultAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'django_version',
        'djangae_version',
        'last_modified',
        'status',
        'score'
    )


class TestAdminSite(admin.AdminSite):
    index_template = "testapp/admin_index.html"

    def __init__(self, *args, **kwargs):
        self.tests = {
            "Counting Performance": test_entity_count_vs_length
        }
        super(TestAdminSite, self).__init__(*args, **kwargs)

    def each_context(self, request):
        return {
            "admin_site": self
        }

    def get_urls(self):
        urls = super(TestAdminSite, self).get_urls()
        my_urls = [
            url(r'^trigger/$', self.trigger_test),
        ]
        return my_urls + urls

    @method_decorator(staff_member_required)
    def trigger_test(self, request):
        try:
            test = self.tests[request.POST["name"]]
        except KeyError:
            raise Http404("Invalid test")

        test()

        return redirect("admin:index")


admin_site = TestAdminSite()
admin_site.register(TestResult, TestResultAdmin)
