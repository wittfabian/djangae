import re, inspect
from django.core.exceptions import ViewDoesNotExist
from django.core.urlresolvers import RegexURLPattern, RegexURLResolver


def extract_views_from_urlpatterns(urlpatterns, base='', namespace=None, ignored_modules=None):
    """
    Return a list of views from a list of urlpatterns.

    Each object in the returned list is a tuple: (view_func, regex, name)
    """
    ignored_modules = ignored_modules if ignored_modules else []
    views = []
    for p in urlpatterns:
        if isinstance(p, RegexURLPattern):
            # Handle correct single URL patterns
            try:
                if namespace:
                    name = '{0}:{1}'.format(namespace, p.name)
                else:
                    name = p.name
                if hasattr(p.callback, '__module__'):
                    if p.callback.__module__.split('.')[0] not in ignored_modules:
                        views.append((p.callback, base + p.regex.pattern, name))
                else:
                    views.append((p.callback, base + p.regex.pattern, name))
            except ViewDoesNotExist:
                continue

        elif isinstance(p, RegexURLResolver):
            # Handle include() definitions
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            views.extend(extract_views_from_urlpatterns(patterns, base + p.regex.pattern,
                namespace=(namespace or p.namespace), ignored_modules=ignored_modules))

        elif hasattr(p, '_get_callback'):
            # Handle string like 'foo.views.view_name' or just function view
            try:
                views.append((p._get_callback(), base + p.regex.pattern, p.name))
            except ViewDoesNotExist:
                continue

        elif hasattr(p, 'url_patterns') or hasattr(p, '_get_url_patterns'):
            # Handle url_patterns objects
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            views.extend(extract_views_from_urlpatterns(patterns, base + p.regex.pattern,
                namespace=namespace, ignored_modules=ignored_modules))
        else:
            raise TypeError("%s does not appear to be a urlpattern object" % p)
    return views


def display_as_table(views):
    """
        Get list of views from dumpurls security management command
        and returns them in the form of table to print in command line
    """
    views = [row.split('||', 3) for row in sorted(views)]
    widths = [len(max(columns, key=len)) for columns in zip(*views)]
    widths = [width  if width < 100 else 100 for width in widths]
    table_views = []

    header = ('URL', 'Handler path', 'Decorators & Mixins')
    table_views.append(
        ' | '.join('{0:<{1}}'.format(title, width) for width, title in zip(widths, header))
    )
    table_views.append('-+-'.join('-' * width for width in widths))

    for row in views:
        if len(row[2]) > 100:
            row[2] = row[2].split(',')
            row[2] = [",".join(row[2][i:i+2]) for i in range(0, len(row[2]), 2)]

        mixins = row[2]
        if type(mixins) == list:
            i = 0
            for line in mixins:
                row[2] = line.strip()
                if i > 0:
                    row[0] = ''
                    row[1] = ''
                table_views.append(
                    ' | '.join('{0:<{1}}'.format(cdata, width) for width, cdata in zip(widths, row))
                )
                i += 1
        else:
            table_views.append(
                ' | '.join('{0:<{1}}'.format(cdata, width) for width, cdata in zip(widths, row))
            )

    return "\n".join([v for v in table_views]) + "\n"


def get_func_name(func):
    if hasattr(func, 'func_name'):
        return func.func_name
    elif hasattr(func, '__name__'):
        return func.__name__
    elif hasattr(func, '__class__'):
        return '%s()' % func.__class__.__name__
    else:
        return re.sub(r' at 0x[0-9a-f]+', '', repr(func))


def get_decorators(func):
    """
        Get function or class and return names of applied decorators
    """
    decorators = []
    if hasattr(func, '__module__'):
        mod = inspect.getmodule(func)
        source_code = inspect.getsourcelines(mod)[0]
        func_name = get_func_name(func)
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

    return decorators


def get_mixins(func, ignored_modules=None):
    """
        Get class and return names and paths to applied mixins
        Has an optional argument for names of modules that should be ignored
    """
    ignored_modules = ignored_modules if ignored_modules else []
    mixins = []
    if hasattr(func, 'cls'):
        for klass in func.cls.mro():
            if klass != func.cls and klass.__module__.split('.')[0] not in ignored_modules:
                mixins.append("{}.{}".format(klass.__module__, get_func_name(klass)))

    return mixins
