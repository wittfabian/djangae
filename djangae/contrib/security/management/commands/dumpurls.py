import functools
import inspect

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse, resolve

from djangae.contrib.security.commands_utils import (
    extract_views_from_urlpatterns,
    display_as_table,
    get_func_name,
    get_decorators,
    get_mixins,
    simplify_regex,
)


DEFAULT_IGNORED_MODULES = ['django', '__builtin__']


class Command(BaseCommand):
    args = "<module_to_ignore> <module_to_ignore> ..."
    help = "Displays all of the url matching routes for the project."

    def handle(self, *args, **options):
        ignored_modules = args if args else DEFAULT_IGNORED_MODULES
        urlconf = __import__(settings.ROOT_URLCONF, {}, {}, [''])
        view_functions = extract_views_from_urlpatterns(urlconf.urlpatterns, ignored_modules=ignored_modules)

        views = []
        for (func, regex, url_name) in view_functions:

            # Extract real function from partial
            if isinstance(func, functools.partial):
                func = func.func

            decorators_and_mixins = get_decorators(func) + get_mixins(func, ignored_modules=ignored_modules)

            parent_class_names = get_parent_class_names(url_name) if url_name else None
            view_info = dict(
                module='{0}.{1}'.format(func.__module__, get_func_name(func)),
                url=simplify_regex(regex),
                decorators=', '.join(decorators_and_mixins),
                parents=', '.join(parent_class_names) if parent_class_names else '',
            )
            views.append(view_info)

        info = (
            "Decorators lists are not comprehensive and do not take account of other patching.\n"
            "Decorators for methods of class-based views are not listed."
        )

        formatting = {
            'default': ("{url}||{module}||{decorators}", ['URL', 'Handler path', 'Decorators & Mixins']),
            'show_parents': ("{url}||{module}||{decorators}||{parents}", ['URL', 'Handler path', 'Decorators & Mixins', 'Parents']),
        }

        line_template, headers = formatting['show_parents']
        formatted_views = [
            line_template.format(**view)
            for view in views
        ]
        table = display_as_table(formatted_views, headers)
        return "\n{0}\n{1}".format(table, info)


def get_parent_class_names(url_name):
    url = reverse(url_name)
    view = resolve(url).func
    if inspect.isclass(view):
        return [
            klass.__name__
            for klass in inspect.getmro(view)
            if klass.__name__ != 'object'
        ]
