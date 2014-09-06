import logging
import yaml
import os
import datetime

_special_indexes = {}
_last_loaded_time = None

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
        #No file, no special index
        logging.info("Not loading any special indexes")
        return

    mtime = os.path.getmtime(index_file)
    if _last_loaded_time and _last_loaded_time == mtime:
        return

    #Load any existing indexes
    with open(index_file, "r") as stream:
        data = yaml.load(stream)

    _special_indexes = data
    _last_loaded_time = mtime

    logging.info("Loaded special indexes for {0} models".format(len(_special_indexes)))


def special_index_exists(model_class, field_name, index_type):
    table = _get_table_from_model(model_class)
    return index_type in _special_indexes.get(table, {}).get(field_name, [])

def special_indexes_for_model(model_class):
    return _special_indexes.get(_get_table_from_model(model_class))

def special_indexes_for_column(model_class, column):
    return _special_indexes.get(_get_table_from_model(model_class), {}).get(column, [])

def write_special_indexes():
    index_file = _get_index_file()

    with open(index_file, "w") as stream:
        stream.write(yaml.dump(_special_indexes))

def add_special_index(model_class, field_name, index_type):
    from djangae.utils import on_production, in_testing
    from django.conf import settings

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
    def validate_can_be_indexed(self, value):
        """Return True if the value is indexable, False otherwise"""
        raise NotImplementedError()

    def prep_value_for_database(self, value): raise NotImplementedError()
    def prep_value_for_query(self, value): raise NotImplementedError()
    def indexed_column_name(self, field_column): raise NotImplementedError()

class IExactIndexer(Indexer):
    def validate_can_be_indexed(self, value):
        return len(value) < 500

    def prep_value_for_database(self, value):
        return value.lower()

    def prep_value_for_query(self, value):
        return value.lower()

    def indexed_column_name(self, field_column):
        return "_idx_iexact_{0}".format(field_column)

class DayIndexer(Indexer):
    def validate_can_be_indexed(self, value):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value):
        if value:
            return value.day
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return value.day
        return value

    def indexed_column_name(self, field_column):
        return "_idx_day_{0}".format(field_column)

class YearIndexer(Indexer):
    def validate_can_be_indexed(self, value):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value):
        if value:
            return value.year
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return value.year
        return value

    def indexed_column_name(self, field_column):
        return "_idx_year_{0}".format(field_column)

class MonthIndexer(Indexer):
    def validate_can_be_indexed(self, value):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value):
        if value:
            return value.month
        return None

    def prep_value_for_query(self, value):
        if isinstance(value, basestring):
            value = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return value.month
        return value

    def indexed_column_name(self, field_column):
        return "_idx_month_{0}".format(field_column)

class WeekDayIndexer(Indexer):
    def validate_can_be_indexed(self, value):
        return isinstance(value, (datetime.datetime, datetime.date))

    def prep_value_for_database(self, value):
        if value:
            zero_based_weekday = value.weekday()
            if zero_based_weekday == 6: #Sunday
                return 1 #Django treats the week as starting at Sunday, but 1 based
            else:
                return zero_based_weekday + 2

        return None

    def prep_value_for_query(self, value):
        return value

    def indexed_column_name(self, field_column):
        return "_idx_week_day_{0}".format(field_column)


REQUIRES_SPECIAL_INDEXES = {
    "iexact": IExactIndexer(),
    "day" : DayIndexer(),
    "month" : MonthIndexer(),
    "year": YearIndexer(),
    "week_day": WeekDayIndexer()
}
