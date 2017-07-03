import logging
import random
import time


def do_with_retry(func, *args, **kwargs):
    """ Tries a function 3 times using exponential backoff
        according to Google API specs.  Optional kwargs:
        `_attempts` - override the number of attempts before giving up.
        `_catch` - tuple of exception types used in `except types as e`.
    """
    MINIMUM_WAIT = 0.5

    _catch = kwargs.pop("_catch", (Exception,))
    _attempts = kwargs.pop('_attempts', 3)

    for n in xrange(_attempts):
        try:
            return func(*args, **kwargs)
        except _catch, e:
            logging.warning("Transient error ({}), retrying...".format(e))
            # back off by factor of two plus a random number of milliseconds
            # to prevent deadlocks (according to API docs..)
            time.sleep(MINIMUM_WAIT + (2 ** n + float(random.randint(0, 1000)) / 1000))
    else:
        raise


def clone_entity(entity, new_key):
    """ Return a clone of the given entity with the key changed to the given key. """
    # TODO: can this be better or less weird?
    # Entity doesn't implement copy()
    entity_as_protobuff = entity.ToPb()
    new_entity = entity.__class__.FromPb(entity_as_protobuff)
    # __key is a protected attribute, so we have to set _Entity__key
    new_entity.__key = new_key
    new_entity._Entity__key = new_key
    return new_entity
