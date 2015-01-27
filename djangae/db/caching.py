from djangae.db.backends.appengine import caching

class DisableCache(object):
    def __init__(self, context=True, memcache=True):
        self.func = None

        self.memcache = memcache
        self.context = context

    def __call__(self, *args, **kwargs):
        def call_func(*_args, **_kwargs):
            try:
                self.__enter__()
                return self.func(*_args, **_kwargs)
            finally:
                self.__exit__()

        if not self.func:
            assert args and callable(args[0])
            self.func = args[0]
            return call_func

        if self.func:
            return call_func(*args, **kwargs)

    def __enter__(self):
        caching.ensure_context()

        self.orig_memcache = caching._context.memcache_enabled
        self.orig_context = caching._context.context_enabled

        caching._context.memcache_enabled = not self.memcache
        caching._context.context_enabled = not self.context

    def __exit__(self, *args, **kwargs):
        caching._context.memcache_enabled = self.orig_memcache
        caching._context.context_enabled = self.orig_context

disable_cache = DisableCache
