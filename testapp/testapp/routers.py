from django.apps import apps

class TestRouter(object):
    """A router for tests that allows setting a model's database explicitly."""

    def _get_db(self, model, **hints):
        return getattr(model, 'test_database', 'default')

    def db_for_read(self, model, **hints):
        return self._get_db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._get_db(model, **hints)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        try:
            model = hints.get('model', apps.get_model(app_label, model_name))
            return db == self._get_db(model)
        except LookupError:
            return False