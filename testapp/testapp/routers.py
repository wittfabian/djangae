class TestRouter(object):
    """A router for tests that allows setting a model's database explicitly."""

    def _get_db(self, model, **hints):
        return getattr(model, 'test_database', None)

    def db_for_read(self, model, **hints):
        return self._get_db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._get_db(model, **hints)
