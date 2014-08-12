from google.appengine.api.datastore import (
    CreateTransactionOptions,
    _GetConnection,
    _PushConnection,
    _PopConnection,
    _SetConnection
)

class AtomicDecorator(object):
    def __init__(self, *args, **kwargs):
        self.func = None
        self.conn = None

        self.xg = kwargs.get("xg")
        self.independent = kwargs.get("independent")

        if len(args) == 1 and callable(args[0]):
            self.func = args[0]

    def _begin(self):
        options = CreateTransactionOptions(
            xg = True if self.xg else False
        )

        self.conn = _GetConnection()
        _PushConnection(None)
        _SetConnection(self.conn.new_transaction(options))

    def _finalize(self):
        _PopConnection()

    def __call__(self, *args, **kwargs):
        def call_func(*_args, **_kwargs):
            try:
                self._begin()
                result = self.func(*_args, **_kwargs)
                _GetConnection().commit()
                return result
            except:
                _GetConnection().rollback()
                raise
            finally:
                self._finalize()

        if not self.func:
            assert args and callable(args[0])
            self.func = args[0]
            return call_func

        if self.func:
            return call_func(*args, **kwargs)


    def __enter__(self):
        self._begin()

    def __exit__(self, *args, **kwargs):
        if len(args) > 1 and isinstance(args[1], Exception):
            _GetConnection().rollback()
        else:
            _GetConnection().commit()

        self._finalize()


atomic = AtomicDecorator
commit_on_success = AtomicDecorator #Alias to the old Django name for this kinda thing
