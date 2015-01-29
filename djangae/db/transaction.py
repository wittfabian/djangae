from google.appengine.api.datastore import (
    CreateTransactionOptions,
    _GetConnection,
    _PushConnection,
    _PopConnection,
    _SetConnection,
    IsInTransaction
)

from google.appengine.datastore.datastore_rpc import TransactionOptions

from djangae.db.backends.appengine import caching


class ContextDecorator(object):
    def __init__(self, func=None):
        self.func = func

    def __call__(self, *args, **kwargs):
        def decorated(*_args, **_kwargs):
            with self:
                return self.func(*_args, **_kwargs)

        if not self.func:
            self.func = args[0]
            return decorated

        return decorated(*args, **kwargs)

class TransactionFailedError(Exception):
    pass

class AtomicDecorator(ContextDecorator):
    def __init__(self, func=None, xg=False, independent=False):
        self.independent = independent
        self.xg = xg
        self.conn_stack = []
        super(AtomicDecorator, self).__init__(func)

    def _do_enter(self, independent, xg):

        if IsInTransaction():
            if independent:
                self.conn_stack.append(_PopConnection())
                try:
                    return self._do_enter(independent, xg)
                except:
                    _PushConnection(self.conn_stack.pop())
                    raise

        options = CreateTransactionOptions(
            xg=xg,
            propagation=TransactionOptions.INDEPENDENT if independent else None
        )

        conn = _GetConnection()
        _PushConnection(None)
        _SetConnection(conn.new_transaction(options))

        # Clear the context cache at the start of a transaction
        caching._context.stack.push()

    def _do_exit(self, independent, xg, exception):
        try:
            if exception:
                _GetConnection().rollback()
            else:
                if not _GetConnection().commit():
                    raise TransactionFailedError()
        finally:
            _PopConnection()

            if independent:
                while self.conn_stack:
                    _PushConnection(self.conn_stack.pop())

                 # Clear the context cache at the end of a transaction
                if exception:
                    caching._context.stack.pop(discard=True)
                else:
                    caching._context.stack.pop(apply_staged=False, clear_staged=False)
            else:
                if exception:
                    caching._context.stack.pop(discard=True)
                else:
                    caching._context.stack.pop(apply_staged=True, clear_staged=True)

    def __enter__(self):
        self._do_enter(self.independent, self.xg)

    def __exit__(self, exc_type, exc_value, traceback):
        self._do_exit(self.independent, self.xg, exc_type)

atomic = AtomicDecorator
commit_on_success = AtomicDecorator  # Alias to the old Django name for this kinda thing
