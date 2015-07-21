import django
from itertools import chain, imap

from djangae.db.utils import (
    get_top_concrete_parent,
)

VALID_QUERY_KINDS = (
    "SELECT",
    "UPDATE",
    "INSERT",
    "DELETE",
    "COUNT",
    "AVERAGE"
)


VALID_CONNECTORS = (
    'AND', 'OR'
)


VALID_OPERATORS = (
    '=', '<', '>', '<=', '>=', 'IN'
)


class WhereNode(object):
    def __init__(self):
        self.column = None
        self.operator = None
        self.value = None

        self.children = []
        self.connector = 'AND'

    @property
    def is_leaf(self):
        return self.column and self.operator

    def set_connector(self, connector):
        self.connector = connector

    def append_child(self, node):
        self.children.append(node)

    def set_leaf(self, column, operator, value):
        self.column = column
        self.operator = operator
        self.value = value

    def __iter__(self):
        for child in chain(*imap(iter, self.children)):
            yield child
        yield self


class Query(object):
    def __init__(self, model, kind):
        assert kind in VALID_QUERY_KINDS

        self.model = model
        self.kind = kind

        self.tables = []
        self.columns = None # None means all fields
        self.distinct_fields = []
        self.order_by = []
        self.row_data = [] # For insert/updates
        self.where = None

    def add_source_table(self, table):
        if table in self.tables:
            return

        self.tables.append(table)

    def add_order_by(self, column):
        self.order_by.append(column)

    def add_row(self, data):
        assert self.columns
        assert len(data) == len(self.columns)

        self.row_data.append(data)

    def set_where(self, where):
        assert where is None or isinstance(where, WhereNode)
        self.where = where


def _transform_query_16(kind, query):
    ret = Query(query.model, kind)
    return ret


def _transform_query_17(kind, query):
    ret = Query(query.model, kind)

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    return ret


def _transform_query_18(kind, query):
    pass


def _transform_query_19(kind, query):
    pass


_FACTORY = {
    (1, 6): _transform_query_16,
    (1, 7): _transform_query_17,
    (1, 8): _transform_query_18,
    (1, 9): _transform_query_19
}


def transform_query(kind, query):
    return _FACTORY[django.VERSION[:2]](kind, query)
