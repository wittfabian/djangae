import django
import logging
import yaml
import os
import datetime
import re

from django.db import models

from djangae import environment
from djangae.fields import iterable
from djangae.sandbox import allow_mode_write
from django.conf import settings

_special_indexes = {}
_last_loaded_time = None

MAX_COLUMNS_PER_SPECIAL_INDEX = getattr(settings, "DJANGAE_MAX_COLUMNS_PER_SPECIAL_INDEX", 3)
CHARACTERS_PER_COLUMN = [31, 44, 54, 63, 71, 79, 85, 91, 97, 103]

STRIP_PERCENTS = django.VERSION < (1, 10)

def _get_index_file():
    index_file = os.path.join(environment.get_application_root(), "djangaeidx.yaml")
    return index_file


def _get_table_from_model(model_class):
    return model_class._meta.db_table.encode("utf-8")


def load_special_indexes():
    global _special_indexes
    global _last_loaded_time

    index_file = _get_index_file()

    if not os.path.exists(index_file):
        # No file, no special index
        logging.debug("Not loading any special indexes")
        return

    mtime = os.path.getmtime(index_file)
    if _last_loaded_time and _last_loaded_time == mtime:
        return

    # Load any existing indexes
    with open(index_file, "r") as stream:
        data = yaml.load(stream)

    _special_indexes = data
    _last_loaded_time = mtime

    logging.debug("Loaded special indexes for %d models", len(_special_indexes))


def special_index_exists(model_class, field_name, index_type):
    table = _get_table_from_model(model_class)
    return index_type in _special_indexes.get(table, {}).get(field_name, [])


def special_indexes_for_model(model_class):
    classes = [ model_class ] + model_class._meta.parents.keys()

    result = {}
    for klass in classes:
        result.update(_special_indexes.get(_get_table_from_model(klass), {}))
    return result


def special_indexes_for_column(model_class, column):
    return special_indexes_for_model(model_class).get(column, [])


def write_special_indexes():
    index_file = _get_index_file()

    with allow_mode_write():
        with open(index_file, "w") as stream:
            stream.write(yaml.dump(_special_indexes))


def add_special_index(model_class, field_name, indexer, operator, value=None):
    from djangae.utils import in_testing
    from django.conf import settings

    index_type = indexer.prepare_index_type(operator, value)

    field_name = field_name.encode("utf-8")  # Make sure we are working with strings

    load_special_indexes()

    if special_index_exists(model_class, field_name, index_type):
        return

    if environment.is_production_environment() or (in_testing() and not getattr(settings, "GENERATE_SPECIAL_INDEXES_DURING_TESTING", False)):
        raise RuntimeError(
            "There is a missing index in your djangaeidx.yaml - \n\n{0}:\n\t{1}: [{2}]".format(
                _get_table_from_model(model_class), field_name, index_type
            )
        )

    _special_indexes.setdefault(
        _get_table_from_model(model_class), {}
    ).setdefault(field_name, []).append(str(index_type))

    write_special_indexes()


class Indexer(object):
    def handles(self, field, operator):
        """
            When given a field instance and an operator (e.g. gt, month__gt etc.)
            returns True or False whether or not this is the indexer to handle that
            situation
        """
        raise NotImplementedError()

    def validate_can_be_indexed(self, value, negated):
        """Return True if the value is indexable, False otherwise"""
        raise NotImplementedError()

    def prep_value_for_database(self, value, index): raise NotImplementedError()
    def prep_value_for_query(self, value): raise NotImplementedError()
    def indexed_column_name(self, field_column, value, index): raise NotImplementedError()
    def prep_query_operator(self, op):
        if "__" in op:
            return op.split("__")[-1]
        else:
            return "exact" # By default do an exact operation

    def prepare_index_type(self, index_type, value): return index_type

    def unescape(self, value):
        value = value.replace("\\_", "_")
        value = value.replace("\\%", "%")
        value = value.replace("\\\\", "\\")
        return value


class StringIndexerMixin(object):
    STRING_FIELDS = (
        models.TextField,
        models.CharField,
        models.URLField,
        models.DateTimeField, # Django allows these for some reason
        models.DateField,
        models.TimeField,
        models.IntegerField, # SQL coerces ints to strings, and so we need these too
        models.PositiveIntegerField,
        models.AutoField
    )

    def handles(self, field, operator):
        try:
            # Make sure the operator is in there
            operator.split("__").index(self.OPERATOR)
        except ValueError:
            return False

        if field.__class__ in self.STRING_FIELDS:
            return True
        elif (field.__class__ in (iterable.ListField, iterable.SetField)
            and field.item_field_type.__class__ in self.STRING_FIELDS and operator.startswith("item__")):
            return True
        return False


class DateIndexerMixin(object):
    def handles(self, field, operator):
        DATE_FIELDS = (
            models.DateField,
            models.DateTimeField
        )

        if operator.split("__")[0] != self.OPERATOR:
            return False

        if field.__class__ in DATE_FIELDS:
            return True
        elif (field.__class__ in (iterable.ListField, iterable.SetField)
            and field.item_field_type.__class__ in DATE_FIELDS and operator.startswith("item__")):
            return True

        return False


class TimeIndexerMixin(object):
    def handles(self, field, operator):
        TIME_FIELDS = (
            models.TimeField,
            models.DateTimeField
        )

        if operator.split("__")[0] != self.OPERATOR:
            return False

        if field.__class__ in TIME_FIELDS:
            return True
        elif (field.__class__ in (iterable.ListField, iterable.SetField)
            and field.item_field_type.__class__ in TIME_FIELDS and operator.startswith("item__")):
            return True

        return False

class IExactIndexer(StringIndexerMixin, Indexer):
    OPERATOR = 'iexact'

    def validate_can_be_indexed(self, value, negated):
        return len(value) < 500

    def prep_value_for_database(self, value, index):
        if value is None:
            return None

        if isinstance(value, (int, long)):
            value = str(value)
        return value.lower()

    def prep_value_for_query(self, value):
        value = self.unescape(value)
        return value.lower()

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iexact_{0}".format(field_column)


class HourIndexer(TimeIndexerMixin, Indexer):
    OPERATOR = 'hour'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, datetime.datetime)

    def prep_value_for_database(self, value, index):
        if value:
            return value.hour
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value.hour

    def indexed_column_name(self, field_column, value, index):
        return "_idx_hour_{0}".format(field_column)


class MinuteIndexer(TimeIndexerMixin, Indexer):
    OPERATOR = 'minute'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, datetime.datetime)

    def prep_value_for_database(self, value, index):
        if value:
            return value.minute
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value.minute

    def indexed_column_name(self, field_column, value, index):
        return "_idx_minute_{0}".format(field_column)


class SecondIndexer(TimeIndexerMixin, Indexer):
    OPERATOR = 'second'
    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, datetime.datetime)

    def prep_value_for_database(self, value, index):
        if value:
            return value.second
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value.second

    def indexed_column_name(self, field_column, value, index):
        return "_idx_second_{0}".format(field_column)


class DayIndexer(DateIndexerMixin, Indexer):
    OPERATOR = 'day'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value, index):
        if value:
            return value.day
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value.day

    def indexed_column_name(self, field_column, value, index):
        return "_idx_day_{0}".format(field_column)


class YearIndexer(DateIndexerMixin, Indexer):
    OPERATOR = 'year'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value, index):
        if value:
            return value.year
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")

        return value.year

    def indexed_column_name(self, field_column, value, index):
        return "_idx_year_{0}".format(field_column)


class MonthIndexer(DateIndexerMixin, Indexer):
    OPERATOR = 'month'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value, index):
        if value:
            return value.month
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, (int, long)):
            return value

        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")

        return value.month

    def indexed_column_name(self, field_column, value, index):
        return "_idx_month_{0}".format(field_column)


class WeekDayIndexer(DateIndexerMixin, Indexer):
    OPERATOR = 'week_day'

    def validate_can_be_indexed(self, value, negated):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value, index):
        if value:
            zero_based_weekday = value.weekday()
            if zero_based_weekday == 6:  # Sunday
                return 1  # Django treats the week as starting at Sunday, but 1 based
            else:
                return zero_based_weekday + 2

        return None

    def prep_value_for_query(self, value):
        return value

    def indexed_column_name(self, field_column, value, index):
        return "_idx_week_day_{0}".format(field_column)


class ContainsIndexer(StringIndexerMixin, Indexer):
    OPERATOR = 'contains'

    def number_of_permutations(self, value):
        return sum(range(len(value)+1))

    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False
        return isinstance(value, basestring) and len(value) <= 500

    def prep_value_for_database(self, value, index):
        result = []
        if value:
            # If this a date or a datetime, or something that supports isoformat, then use that
            if hasattr(value, "isoformat"):
                value = value.isoformat()

            if self.number_of_permutations(value) > MAX_COLUMNS_PER_SPECIAL_INDEX*500:
                raise ValueError("Can't index for contains query, this value is too long and has too many permutations. \
                    You can increase the DJANGAE_MAX_COLUMNS_PER_SPECIAL_INDEX setting to fix that. Use with caution.")
            if len(value) > CHARACTERS_PER_COLUMN[-1]:
                raise ValueError("Can't index for contains query, this value can be maximum {0} characters long.".format(CHARACTERS_PER_COLUMN[-1]))

            if hasattr(value, '__iter__'):  # is a list, tuple or set?
                for element in value:
                    length = len(element)
                    lists = [element[i:j + 1] for i in xrange(length) for j in xrange(i, length)]
                    result.extend(lists)
            else:
                length = len(value)
                lists = [value[i:j + 1] for i in xrange(length) for j in xrange(i, length)]
                result.extend(lists)
                result = [e for e in set(result)]

        return result or None

    def prep_value_for_query(self, value):
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        else:
            value = unicode(value)
        value = self.unescape(value)

        if STRIP_PERCENTS:
            if value.startswith("%") and value.endswith("%"):
                value = value[1:-1]

        return value

    def indexed_column_name(self, field_column, value, index):
        # This we use when we actually query to return the right field for a given
        # value length
        length = len(value)
        column_number = 0
        for x in CHARACTERS_PER_COLUMN:
            if length > x:
                column_number += 1
        return "_idx_contains_{0}_{1}".format(field_column, column_number)

    def prep_query_operator(self, op):
        return "exact"


class IContainsIndexer(ContainsIndexer):
    OPERATOR = 'icontains'

    def prep_value_for_database(self, value, index):
        if value is None:
            return None
        if hasattr(value, '__iter__'):  # is a list, tuple or set?
            value = [v.lower() for v in value]
        else:
            value = value.lower()
        result = super(IContainsIndexer, self).prep_value_for_database(value, index)
        return result if result else None

    def indexed_column_name(self, field_column, value, index):
        column_name = super(IContainsIndexer, self).indexed_column_name(field_column, value, index)
        return column_name.replace('_idx_contains_', '_idx_icontains_')

    def prep_value_for_query(self, value):
        return super(IContainsIndexer, self).prep_value_for_query(value).lower()


class EndsWithIndexer(StringIndexerMixin, Indexer):
    """
        dbindexer originally reversed the string and did a startswith on it.
        However, this is problematic as it uses an inequality and therefore
        limits the queries you can perform. Instead, we store all permutations
        of the last characters in a list field. Then we can just do an exact lookup on
        the value. Which isn't as nice, but is more flexible.
    """
    OPERATOR = 'endswith'

    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False

        return isinstance(value, basestring) and len(value) < 500

    def prep_value_for_database(self, value, index):
        results = []
        for i in xrange(len(value)):
            results.append(value[i:])
        return results or None

    def prep_value_for_query(self, value):
        value = self.unescape(value)
        if STRIP_PERCENTS:
            if value.startswith("%"):
                value = value[1:]
        return value

    def indexed_column_name(self, field_column, value, index):
        return "_idx_endswith_{0}".format(field_column)


class IEndsWithIndexer(EndsWithIndexer):
    """
        Same as above, just all lower cased
    """
    OPERATOR = 'iendswith'

    def prep_value_for_database(self, value, index):
        if value is None:
            return None
        result = super(IEndsWithIndexer, self).prep_value_for_database(value.lower(), index)
        return result or None

    def prep_value_for_query(self, value):
        return super(IEndsWithIndexer, self).prep_value_for_query(value.lower())

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iendswith_{0}".format(field_column)


class StartsWithIndexer(StringIndexerMixin, Indexer):
    """
        Although we can do a startswith natively, doing it this way allows us to
        use more queries (E.g. we save an exclude)
    """
    OPERATOR = 'startswith'

    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False

        return isinstance(value, basestring) and len(value) < 500

    def prep_value_for_database(self, value, index):
        if value is None:
            return None

        if isinstance(value, datetime.datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")

        results = []
        if hasattr(value, '__iter__'):  # is a list, tuple or set?
            for element in value:
                for i in xrange(1, len(element) + 1):
                    results.append(element[:i])
        else:
            for i in xrange(1, len(value) + 1):
                results.append(value[:i])

        if not results:
            return None
        return results

    def prep_value_for_query(self, value):
        value = self.unescape(value)
        if STRIP_PERCENTS:
            if value.endswith("%"):
                value = value[:-1]
        return value

    def indexed_column_name(self, field_column, value, index):
        return "_idx_startswith_{0}".format(field_column)

    def prep_query_operator(self, op):
        return "exact"


class IStartsWithIndexer(StartsWithIndexer):
    """
        Same as above, just all lower cased
    """
    OPERATOR = 'istartswith'

    def prep_value_for_database(self, value, index):
        if value:
            if hasattr(value, '__iter__'):  # is a list, tuple or set?
                value = [v.lower() for v in value]
            else:
                value = value.lower()
        return super(IStartsWithIndexer, self).prep_value_for_database(value, index)

    def prep_value_for_query(self, value):
        return super(IStartsWithIndexer, self).prep_value_for_query(value.lower())

    def indexed_column_name(self, field_column, value, index):
        return "_idx_istartswith_{0}".format(field_column)


class RegexIndexer(StringIndexerMixin, Indexer):
    OPERATOR = 'regex'

    def prepare_index_type(self, index_type, value):
        """
            If we're dealing with RegexIndexer, we create a new index for each
            regex pattern. Indexes are called regex__pattern.
        """
        return '{}__{}'.format(index_type, value.encode("utf-8").encode('hex'))

    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False

        return isinstance(value, bool)

    def get_pattern(self, index):
        try:
            return index.split('__')[-1].decode('hex').decode("utf-8")
        except IndexError:
            return ''

    def check_if_match(self, value, index, flags=0):
        pattern = self.get_pattern(index)

        if value:
            if hasattr(value, '__iter__'): # is a list, tuple or set?
                if any([bool(re.search(pattern, x, flags)) for x in value]):
                    return True
            else:
                if isinstance(value, (int, long)):
                    value = str(value)

                return bool(re.search(pattern, value, flags))
        return False

    def prep_value_for_database(self, value, index):
        return self.check_if_match(value, index)

    def prep_value_for_query(self, value):
        return True

    def indexed_column_name(self, field_column, value, index):
        return "_idx_regex_{0}_{1}".format(field_column, self.get_pattern(index).encode("utf-8").encode('hex'))

    def prep_query_operator(self, op):
        return "exact"


class IRegexIndexer(RegexIndexer):
    OPERATOR = 'iregex'

    def prepare_index_type(self, index_type, value):
        return '{}__{}'.format(index_type, value.encode('hex'))

    def prep_value_for_database(self, value, index):
        return self.check_if_match(value, index, flags=re.IGNORECASE)

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iregex_{0}_{1}".format(field_column, self.get_pattern(index).encode('hex'))


_REGISTERED_INDEXERS = []

def register_indexer(indexer_class):
    global _REGISTERED_INDEXERS
    _REGISTERED_INDEXERS.append(indexer_class())


def get_indexer(field, operator):
    global _REGISTERED_INDEXERS

    for indexer in _REGISTERED_INDEXERS:
        if indexer.handles(field, operator):
            return indexer


register_indexer(IExactIndexer)
register_indexer(ContainsIndexer)
register_indexer(IContainsIndexer)
register_indexer(HourIndexer)
register_indexer(MinuteIndexer)
register_indexer(SecondIndexer)
register_indexer(DayIndexer)
register_indexer(MonthIndexer)
register_indexer(YearIndexer)
register_indexer(WeekDayIndexer)
register_indexer(EndsWithIndexer)
register_indexer(IEndsWithIndexer)
register_indexer(StartsWithIndexer)
register_indexer(IStartsWithIndexer)
register_indexer(RegexIndexer)
register_indexer(IRegexIndexer)
