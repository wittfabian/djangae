# Sleuth - a Simple mocking library

# USAGE:

#  with sleuth.watch("some.path.to.thing") as mock:
#      thing()
#      self.assertTrue(mock.called)

#  with sleuth.switch("some.path.to.thing", lambda x: pass) as mock:
#

def _dot_lookup(thing, comp, import_path):
    try:
        return getattr(thing, comp)
    except AttributeError:
        __import__(import_path)
        return getattr(thing, comp)


def _evaluate_path(target):
    components = target.split('.')
    import_path = components.pop(0)
    thing = __import__(import_path)

    for comp in components:
        import_path += ".%s" % comp
        thing = _dot_lookup(thing, comp, import_path)
    return thing

def _patch(path, replacement):
    thing = _evaluate_path(
        ".".join(path.split(".")[:-1])
    )
    setattr(thing, path.split(".")[-1], replacement)

class Mock(object):

    def __getattr__(self, name):
        return Mock()

    def __setattr__(self, name, value):
        pass

    def __repr__(self):
        return "<Mock %s>" % id(self)


class Watch(object):
    def __init__(self, func_path):
        self._original_func = _evaluate_path(func_path)
        self._func_path = func_path

        if not hasattr(self._original_func, "__call__"):
            raise TypeError("Tried to watch something that isn't a callable")

        def wrapper(_func):
            def wrapped(*args, **kwargs):
                wrapped.call_count += 1
                wrapped.calls.append(
                    (args, kwargs)
                )
                return _func(*args, **kwargs)

            wrapped.call_count = 0
            wrapped.calls = []

            return wrapped

        self._mock = wrapper(self._original_func)

    def __enter__(self):
        _patch(self._func_path, self._mock)

        return self._mock

    def __exit__(self, *args, **kwargs):
        _patch(self._func_path, self._original_func)

watch = Watch


class Switch(object):
    def __init__(self, func_path, replacement):
        self._original_func = _evaluate_path(func_path)
        self._func_path = func_path
        self._replacement = replacement
        self._watch = None

    def __enter__(self):
        _patch(self._func_path, self._replacement)
        self._watch = watch(self._func_path)
        return self._watch.__enter__()

    def __exit__(self, *args, **kwargs):
        self._watch.__exit__()
        _patch(self._func_path, self._original_func)

switch = Switch
