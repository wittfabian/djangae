from django.core.cache.backends.memcached import BaseMemcachedCache


class AppEngineMemcacheCache(BaseMemcachedCache):
    """
    Cache backend using App Engine's memcache service
    """
    def __init__(self, server, params):
        from google.appengine.api import memcache
        super(AppEngineMemcacheCache, self).__init__(
            server,
            params,
            library=memcache,
            value_not_found_exception=ValueError
        )
