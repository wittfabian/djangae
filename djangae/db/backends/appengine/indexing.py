import logging
import yaml
import os
import datetime
import re

from djangae.sandbox import allow_mode_write
from django.conf import settings

_special_indexes = {}
_last_loaded_time = None

MAX_COLUMNS_PER_SPECIAL_INDEX = getattr(settings, "DJANGAE_MAX_COLUMNS_PER_SPECIAL_INDEX", 3)
CHARACTERS_PER_COLUMN = [31, 44, 54, 63, 71, 79, 85, 91, 97, 103]

def _get_index_file():
    from djangae.utils import find_project_root
    index_file = os.path.join(find_project_root(), "djangaeidx.yaml")

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

    logging.debug("Loaded special indexes for {0} models".format(len(_special_indexes)))


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


def add_special_index(model_class, field_name, index_type, value=None):
    from djangae.utils import on_production, in_testing
    from django.conf import settings

    indexer = REQUIRES_SPECIAL_INDEXES[index_type]
    index_type = indexer.prepare_index_type(index_type, value)

    field_name = field_name.encode("utf-8")  # Make sure we are working with strings

    load_special_indexes()

    if special_index_exists(model_class, field_name, index_type):
        return

    if on_production() or (in_testing() and not getattr(settings, "GENERATE_SPECIAL_INDEXES_DURING_TESTING", False)):
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
    def validate_can_be_indexed(self, value, negated):
        """Return True if the value is indexable, False otherwise"""
        raise NotImplementedError()

    def prep_value_for_database(self, value, index): raise NotImplementedError()
    def prep_value_for_query(self, value): raise NotImplementedError()
    def indexed_column_name(self, field_column, value, index): raise NotImplementedError()
    def prep_query_operator(self, op): return "exact"
    def prepare_index_type(self, index_type, value): return index_type

    def unescape(self, value):
        value = value.replace("\\_", "_")
        value = value.replace("\\%", "%")
        value = value.replace("\\\\", "\\")
        return value


class IExactIndexer(Indexer):
    def validate_can_be_indexed(self, value, negated):
        return len(value) < 500

    def prep_value_for_database(self, value, index):
        if value is None:
            return None

        if isinstance(value, (int, long)):
            value = str(value)
        return value.lower()

    def prep_value_for_query(self, value):
        return value.lower()

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iexact_{0}".format(field_column)


class DayIndexer(Indexer):
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


class YearIndexer(Indexer):
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


class MonthIndexer(Indexer):
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


class WeekDayIndexer(Indexer):
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


class ContainsIndexer(Indexer):
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

            length = len(value)
            result = list(set([value[i:j + 1] for i in xrange(length) for j in xrange(i, length)]))

        return result or None

    def prep_value_for_query(self, value):
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        else:
            value = unicode(value)
        value = self.unescape(value)
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

class IContainsIndexer(ContainsIndexer):
    def prep_value_for_database(self, value, index):
        if value is None:
            return None
        result = super(IContainsIndexer, self).prep_value_for_database(value.lower(), index)
        return result if result else None

    def indexed_column_name(self, field_column, value, index):
        column_name = super(IContainsIndexer, self).indexed_column_name(field_column, value, index)
        return column_name.replace('_idx_contains_', '_idx_icontains_')

    def prep_value_for_query(self, value):
        return super(IContainsIndexer, self).prep_value_for_query(value).lower()


class EndsWithIndexer(Indexer):
    """
        dbindexer originally reversed the string and did a startswith on it.
        However, this is problematic as it uses an inequality and therefore
        limits the queries you can perform. Instead, we store all permutations
        of the last characters in a list field. Then we can just do an exact lookup on
        the value. Which isn't as nice, but is more flexible.
    """
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
        if value.startswith("%"):
            value = value[1:]
        return value

    def indexed_column_name(self, field_column, value, index):
        return "_idx_endswith_{0}".format(field_column)


class IEndsWithIndexer(EndsWithIndexer):
    """
        Same as above, just all lower cased
    """
    def prep_value_for_database(self, value, index):
        if value is None:
            return None
        result = super(IEndsWithIndexer, self).prep_value_for_database(value.lower(), index)
        return result or None

    def prep_value_for_query(self, value):
        return super(IEndsWithIndexer, self).prep_value_for_query(value.lower())

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iendswith_{0}".format(field_column)


class StartsWithIndexer(Indexer):
    """
        Although we can do a startswith natively, doing it this way allows us to
        use more queries (E.g. we save an exclude)
    """
    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False

        return isinstance(value, basestring) and len(value) < 500

    def prep_value_for_database(self, value, index):
        if isinstance(value, datetime.datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")

        results = []
        for i in xrange(1, len(value) + 1):
            results.append(value[:i])

        if not results:
            return None
        return results

    def prep_value_for_query(self, value):
        value = self.unescape(value)
        if value.endswith("%"):
            value = value[:-1]

        return value

    def indexed_column_name(self, field_column, value, index):
        return "_idx_startswith_{0}".format(field_column)


class IStartsWithIndexer(StartsWithIndexer):
    """
        Same as above, just all lower cased
    """
    def prep_value_for_database(self, value, index):
        return super(IStartsWithIndexer, self).prep_value_for_database(value.lower(), index)

    def prep_value_for_query(self, value):
        return super(IStartsWithIndexer, self).prep_value_for_query(value.lower())

    def indexed_column_name(self, field_column, value, index):
        return "_idx_istartswith_{0}".format(field_column)


class RegexIndexer(Indexer):

    def prepare_index_type(self, index_type, value):
        """
            If we're dealing with RegexIndexer, we create a new index for each
            regex pattern. Indexes are called regex__pattern.
        """
        return 'regex__{}'.format(value.encode("utf-8").encode('hex'))

    def validate_can_be_indexed(self, value, negated):
        if negated:
            return False

        return isinstance(value, bool)

    def get_pattern(self, index):
        try:
            return index.split('__')[1].decode('hex').decode("utf-8")
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


class IRegexIndexer(RegexIndexer):

    def prepare_index_type(self, index_type, value):
        return 'iregex__{}'.format(value.encode('hex'))

    def prep_value_for_database(self, value, index):
        return self.check_if_match(value, index, flags=re.IGNORECASE)

    def indexed_column_name(self, field_column, value, index):
        return "_idx_iregex_{0}_{1}".format(field_column, self.get_pattern(index).encode('hex'))


REQUIRES_SPECIAL_INDEXES = {
    "iexact": IExactIndexer(),
    "contains": ContainsIndexer(),
    "icontains": IContainsIndexer(),
    "day" : DayIndexer(),
    "month" : MonthIndexer(),
    "year": YearIndexer(),
    "week_day": WeekDayIndexer(),
    "endswith": EndsWithIndexer(),
    "iendswith": IEndsWithIndexer(),
    "startswith": StartsWithIndexer(),
    "istartswith": IStartsWithIndexer(),
    "regex": RegexIndexer(),
    "iregex": IRegexIndexer(),
}
