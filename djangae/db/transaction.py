import copy

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


def in_atomic_block():
    # At the moment just a wrapper around App Engine so that
    # users don't have to use two different APIs
    return IsInTransaction()


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
    def __init__(self, func=None, xg=False, independent=False, mandatory=False):
        self.independent = independent
        self.xg = xg
        self.mandatory = mandatory
        self.conn_stack = []
        self.transaction_started = False
        super(AtomicDecorator, self).__init__(func)

    def _do_enter(self):
        if IsInTransaction():
            if self.independent:
                self.conn_stack.append(_PopConnection())
                try:
                    return self._do_enter()
                except:
                    _PushConnection(self.conn_stack.pop())
                    raise
            else:
                # App Engine doesn't support nested transactions, so if there is a nested
                # atomic() call we just don't do anything. This is how RunInTransaction does it
                return
        elif self.mandatory:
            raise TransactionFailedError("You've specified that an outer transaction is mandatory, but one doesn't exist")

        options = CreateTransactionOptions(
            xg=self.xg,
            propagation=TransactionOptions.INDEPENDENT if self.independent else None
        )

        conn = _GetConnection()

        self.transaction_started = True
        new_conn = conn.new_transaction(options)

        _PushConnection(None)
        _SetConnection(new_conn)

        assert(_GetConnection())

        # Clear the context cache at the start of a transaction
        caching._context.stack.push()

    def _do_exit(self, exception):
        if not self.transaction_started:
            # If we didn't start a transaction, then don't roll back or anything
            return

        try:
            if exception:
                _GetConnection().rollback()
            else:
                if not _GetConnection().commit():
                    raise TransactionFailedError()
        finally:
            _PopConnection()

            if self.independent:
                while self.conn_stack:
                    _PushConnection(self.conn_stack.pop())

             # Clear the context cache at the end of a transaction
            if exception:
                caching._context.stack.pop(discard=True)
            else:
                caching._context.stack.pop(apply_staged=True, clear_staged=True)


    def __enter__(self):
        self._do_enter()

    def __exit__(self, exc_type, exc_value, traceback):
        self._do_exit(exc_type)

atomic = AtomicDecorator
commit_on_success = AtomicDecorator  # Alias to the old Django name for this kinda thing


class NonAtomicDecorator(ContextDecorator):
    def _do_enter(self):
        self._original_connection = None

        if not in_atomic_block():
            return # Do nothing if we aren't even in a transaction

        self._original_connection = _PopConnection()
        self._original_context = copy.deepcopy(caching._context)

        while len(caching._context.stack.stack) > 1:
            caching._context.stack.pop(discard=True)


    def _do_exit(self, exception):
        if self._original_connection:
            _PushConnection(self._original_connection)
            caching._context = self._original_context

    def __enter__(self):
        self._do_enter()

    def __exit__(self, exc_type, exc_value, traceback):
        self._do_exit(exc_type)

non_atomic = NonAtomicDecorator
