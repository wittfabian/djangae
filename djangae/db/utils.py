#STANDARD LIB
from datetime import datetime
from decimal import Decimal
#LIBRARIES
from django.conf import settings
from django.db.backends.util import format_number
from django.utils import timezone


def make_timezone_naive(value):
    if value is None:
        return None

    if timezone.is_aware(value):
        if settings.USE_TZ:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            raise ValueError("Djangae backend does not support timezone-aware datetimes when USE_TZ is False.")
    return value


def decimal_to_string(value, max_digits=16, decimal_places=0):
    """
    Converts decimal to a unicode string for storage / lookup by nonrel
    databases that don't support decimals natively.

    This is an extension to `django.db.backends.util.format_number`
    that preserves order -- if one decimal is less than another, their
    string representations should compare the same (as strings).

    TODO: Can't this be done using string.format()?
          Not in Python 2.5, str.format is backported to 2.6 only.
    """

    # Handle sign separately.
    if value.is_signed():
        sign = u'-'
        value = abs(value)
    else:
        sign = u''

    # Let Django quantize and cast to a string.
    value = format_number(value, max_digits, decimal_places)

    # Pad with zeroes to a constant width.
    n = value.find('.')
    if n < 0:
        n = len(value)
    if n < max_digits - decimal_places:
        value = u'0' * (max_digits - decimal_places - n) + value
    return sign + value


def normalise_field_value(value):
    """ Converts a field value to a common type/format to make comparable to another. """
    if isinstance(value, datetime):
        return make_timezone_naive(value)
    elif isinstance(value, Decimal):
        return decimal_to_string(value)
    return value
