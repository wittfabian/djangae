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
        self.negated = False

    @property
    def is_leaf(self):
        return bool(self.column and self.operator)

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

    @property
    def is_normalized(self):
        """
            Returns True if this query has a normalized where tree
        """
        if not self.where:
            return True

        # Only a leaf node, return True
        if not self.where.is_leaf:
            return True

        # If we have children, and they are all leaf nodes then this is a normalized
        # query
        return self.where.connector == 'OR' and self.where.children and all(x.is_leaf for x in self.where.children)

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


def _transform_query_17(connection, kind, query):
    ret = Query(query.model, kind)

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    output = WhereNode()
    output.connector = query.where.connector

    def walk_tree(source_node, new_parent):
        for child in source_node.children:
            new_node = WhereNode()

            if not getattr(child, "children", None):
                # Leaf
                lhs = child.lhs.output_field.column
                rhs = child.lhs.output_field.get_db_prep_lookup(
                    child.lookup_name,
                    child.rhs,
                    connection,
                    prepared=True
                )[0]

                new_node.column = lhs
                new_node.operator = child.lookup_name
                new_node.value = rhs
            else:
                new_node.connector = child.connector
                walk_tree(child, new_node)

            new_parent.children.append(new_node)

    walk_tree(query.where, output)

    # If there no child nodes, just wipe out the where
    if not output.children:
        output = None

    ret.where = output

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


def transform_query(compiler, kind, query):
    return _FACTORY[django.VERSION[:2]](compiler, kind, query)
