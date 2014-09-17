import hashlib
from google.appengine.api import datastore
from google.appengine.api.datastore import (
    CreateTransactionOptions,
    _GetConnection,
    _PushConnection,
    _PopConnection,
    _SetConnection,
    IsInTransaction
)
from google.appengine.api import memcache

from google.appengine.datastore.datastore_rpc import TransactionOptions

class AtomicDecorator(object):
    def __init__(self, *args, **kwargs):
        self.func = None

        self.xg = kwargs.get("xg")
        self.independent = kwargs.get("independent")
        self.parent_conn = None

        if len(args) == 1 and callable(args[0]):
            self.func = args[0]

    def _begin(self):
        options = CreateTransactionOptions(
            xg = True if self.xg else False,
            propagation = TransactionOptions.INDEPENDENT if self.independent else None
        )

        if IsInTransaction() and not self.independent:
            raise RuntimeError("Nested transactions are not supported")
        elif self.independent:
            #If we're running an independent transaction, pop the current one
            self.parent_conn = _PopConnection()

        #Push a new connection, start a new transaction
        conn = _GetConnection()
        _PushConnection(None)
        _SetConnection(conn.new_transaction(options))

    def _finalize(self):
        _PopConnection() #Pop the transaction connection
        if self.parent_conn:
            #If there was a parent transaction, now put that back
            _PushConnection(self.parent_conn)
            self.parent_conn = None

    def __call__(self, *args, **kwargs):
        def call_func(*_args, **_kwargs):
            try:
                self._begin()
                result = self.func(*_args, **_kwargs)
                _GetConnection().commit()
                return result
            except:
                conn = _GetConnection()
                if conn:
                    conn.rollback()
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
            _GetConnection().rollback() #If an exception happens, rollback
        else:
            _GetConnection().commit() #Otherwise commit

        self._finalize()


atomic = AtomicDecorator
commit_on_success = AtomicDecorator #Alias to the old Django name for this kinda thing



def idempotent_transaction(func, *args, **kwargs):
    """ Runs the given function inside a Datastore transaction, while dealing
        with the fact that the Datastore behaviour states that even if a
        transaction fails it may later successfully complete in the background.

        This function ensures that so long as you run your transaction via this
        function, it can only ever be applied once, even if you run it multiple
        times.

        A caveat of this is that you cannot guarantee getting the return result
        of your function (because it may succeed in the background).

        By deafult each transaction will be identified by the function, its args
        and kwargs, but if you want to better identify transactions (which may
        be useful if you want to retry transactions if/when they fail) then you
        can pass a `transation_id` argument, which should be a string.
    """
    transaction_id = kwargs.pop('transaction_id', None)
    if not transaction_id:
        transaction_id = make_transaction_id(func, args, kwargs)

    def transaction():
        # Check to see if this transaction has been run before
        marker = get_marker(transaction_id)
        if marker:
            raise TransactionAlreadyApplied(
                "Transaction %s for function '%s' already marked as done."
                % (transaction_id, func.__name__)
            )
        # else... if we're good to run the transaction:
        return func(*args, **kwargs)
        # Set the transaction marker, note that this is done inside the same
        # transaction that we run the function in.
        set_marker(transaction_id)

    # Note: we don't necessarily need this loop here.  We could just allow the
    # calling code to retry, there's no reason we should do retries here, other
    # than for convenience.
    max_attemps = 5
    attempts = 0
    while attempts < max_attemps:
        try:
            return datastore.RunInTransaction(transaction)
        except datastore.TransactionFailedError:
            attempts += 1
    # If we got to here then we exhausted the max attempts, so just raise the
    # last exception and allow the calling code to decide if it wants to retry.
    raise


def make_transaction_id(func, args, kwargs):
    """ Hash the given function, args and kwargs into some kind of string-y ID. """
    # TODO: this will probably die in some cases and could probably be improved.
    return hashlib.md5(
        str(func)
        + u"".join(unicode(a) for a in args).encode("utf-8")
        + u"".join(unicode(k) + unicode(v) for k, v in kwargs.items()).encode('utf-8')
    ).hexdigest()


def get_marker(transaction_id):
    """ If a marker for the given transaction_id exists, return it.
        This uses memcache for speed and as an extra layer of protection, but
        falls back to the Datastore for robustness.
    """
    datastore_key = get_datastore_key(transaction_id)
    return memcache.get(transaction_id) or datastore.Get(datastore_key) or None


def set_marker(transaction_id):
    """ Set the given marker in both the Datastore and memcache. """
    datastore_key = get_datastore_key(transaction_id)
    datastore.Put(datastore_key)
    memcache.set(transaction_id, True)


def get_datastore_key(transaction_id):
    return datastore.Key.from_path(
        'djangae_transaction_marker', transaction_id
    )


class TransactionAlreadyApplied(Exception):
    pass
