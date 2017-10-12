import ast
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

    def add_arguments(self, parser):
        parser.add_argument('--show_allowed_methods', action='store_true')
        parser.add_argument('--show_class_parents', action='store_true')

    def handle(self, *args, **options):
        show_class_parents = options.get('show_class_parents')
        show_allowed_methods = options.get('show_allowed_methods')

        ignored_modules = args if args else DEFAULT_IGNORED_MODULES
        urlconf = __import__(settings.ROOT_URLCONF, {}, {}, [''])
        view_functions = extract_views_from_urlpatterns(urlconf.urlpatterns, ignored_modules=ignored_modules)

        views = []
        for (func, regex, url_name) in view_functions:

            # Extract real function from partial
            if isinstance(func, functools.partial):
                func = func.func

            decorators_and_mixins = get_decorators(func) + get_mixins(func, ignored_modules=ignored_modules)

            view_info = dict(
                module='{0}.{1}'.format(func.__module__, get_func_name(func)),
                url=simplify_regex(regex),
                decorators=', '.join(decorators_and_mixins),
            )

            cbv_info = {}
            if url_name:
                cbv_info = get_cbv_info(url_name)

            view_info.update({
                'parents': ', '.join(cbv_info.get('parent_class_names', [])),
                'allowed_http_methods': ', '.join(cbv_info.get('allowed_http_methods', [])),
            })

            decorators = cbv_info.get('decorators')
            if decorators:
                view_info['decorators'] = decorators

            views.append(view_info)

        info = (
            "Decorators lists are not comprehensive and do not take account of other patching.\n"
        )

        headers = ['URL', 'Handler path', 'Decorators & Mixins']
        line_template = "{url}||{module}||{decorators}"

        if show_class_parents:
            headers += ['Parents']
            line_template += '||{parents}'

        if show_allowed_methods:
            headers += ['Allowed Methods']
            line_template += '||{allowed_http_methods}'

        formatted_views = [
            line_template.format(**view)
            for view in views
        ]
        table = display_as_table(formatted_views, headers)
        return "\n{0}\n{1}".format(table, info)


def get_cbv_info(url_name):
    url = reverse(url_name)
    view = resolve(url).func
    is_class_based_view = inspect.isclass(view)

    if is_class_based_view:
        return {
            'decorators':  _get_class_decorators(view),
            'allowed_http_methods': view.http_method_names,
            'parent_class_names': [
                klass.__name__
                for klass in inspect.getmro(view)
                if klass.__name__ != 'object'
            ],
        }

    # function based view
    return {}


def _get_class_decorators(cls):
    # from https://stackoverflow.com/a/31197273
    target = cls
    decorators = {}

    def visit_FunctionDef(node):
        decorators[node.name] = []
        for n in node.decorator_list:
            name = ''
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
            else:
                name = n.attr if isinstance(n, ast.Attribute) else n.id

            decorators[node.name].append(name)

    node_iter = ast.NodeVisitor()
    node_iter.visit_FunctionDef = visit_FunctionDef
    node_iter.visit(ast.parse(inspect.getsource(target)))
    return decorators
