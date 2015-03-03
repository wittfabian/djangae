import inspect
import functools
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.admindocs.views import simplify_regex
from djangae.contrib.security.commands_utils import (
    extract_views_from_urlpatterns,
    display_as_table,
    get_func_name
)


DEFAULT_IGNORED_MODULES = ['django', '__builtin__']


class Command(BaseCommand):
    args = "<module_to_ignore> <module_to_ignore> ..."
    help = "Displays all of the url matching routes for the project."

    def handle(self, *args, **options):
        ignored_modules = args if args else DEFAULT_IGNORED_MODULES
        views = []
        urlconf = __import__(settings.ROOT_URLCONF, {}, {}, [''])
        view_functions = extract_views_from_urlpatterns(urlconf.urlpatterns, ignored_modules=ignored_modules)

        for (func, regex, url_name) in view_functions:
            # Extract real function from partial
            if isinstance(func, functools.partial):
                func = func.func

            # Name of the function / class
            func_name = get_func_name(func)

            # Decorators
            decorators = []
            if hasattr(func, '__module__'):
                mod = inspect.getmodule(func)
                source_code = inspect.getsourcelines(mod)[0]
                i = 0

                for line in source_code:
                    if line.startswith('def {}'.format(func_name)) or line.startswith('class {}'.format(func_name)):
                        j = 1
                        k = source_code[i-j]
                        while k.startswith('@'):
                            decorators.append(k.strip().split('(')[0])
                            j += 1
                            k = source_code[i-j]
                    i += 1

            # Mixins
            mixins = []
            if hasattr(func, 'cls'):
                for klass in func.cls.mro():
                    if klass != func.cls and klass.__module__.split('.')[0] not in ignored_modules:
                        mixins.append("{}.{}".format(klass.__module__, get_func_name(klass)))

            # Collect information
            views.append("{url}||{module}||{decorators}".format(
                module='{0}.{1}'.format(func.__module__, func_name),
                url=simplify_regex(regex),
                decorators=', '.join(decorators+mixins)
            ))

        return display_as_table(views)
