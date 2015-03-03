import re
from django.core.exceptions import ViewDoesNotExist
from django.core.urlresolvers import RegexURLPattern, RegexURLResolver


def extract_views_from_urlpatterns(urlpatterns, base='', namespace=None, ignored_modules=[]):
    """
    Return a list of views from a list of urlpatterns.

    Each object in the returned list is a two-tuple: (view_func, regex)
    """
    views = []
    for p in urlpatterns:
        if isinstance(p, RegexURLPattern):
            try:
                if not p.name:
                    name = p.name
                elif namespace:
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
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            views.extend(extract_views_from_urlpatterns(patterns, base + p.regex.pattern,
                namespace=(namespace or p.namespace), ignored_modules=ignored_modules))
        elif hasattr(p, '_get_callback'):
            try:
                views.append((p._get_callback(), base + p.regex.pattern, p.name))
            except ViewDoesNotExist:
                continue
        elif hasattr(p, 'url_patterns') or hasattr(p, '_get_url_patterns'):
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
    if hasattr(func, '__name__'):
        return func.__name__
    elif hasattr(func, '__class__'):
        return '%s()' % func.__class__.__name__
    else:
        return re.sub(r' at 0x[0-9a-f]+', '', repr(func))
