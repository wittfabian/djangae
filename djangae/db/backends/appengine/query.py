import django
import json
import logging

from django.core.exceptions import FieldError
from django.db.models.fields import FieldDoesNotExist
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql.where import EmptyWhere
from django.db.models import AutoField
from itertools import chain, imap

from djangae.utils import on_production
from djangae.db.utils import (
    get_top_concrete_parent,
    get_concrete_parents
)


DJANGAE_LOG = logging.getLogger("djangae")


VALID_QUERY_KINDS = (
    "SELECT",
    "UPDATE",
    "INSERT",
    "DELETE",
    "COUNT",
    "AVERAGE"
)

VALID_ANNOTATIONS = {
    "MIN": min,
    "MAX": max,
    "SUM": sum,
    "COUNT": len,
    "AVG": lambda x: (sum(x) / len(x))
}

VALID_CONNECTORS = (
    'AND', 'OR'
)


VALID_OPERATORS = (
    '=', '<', '>', '<=', '>=', 'IN'
)

def convert_operator(operator):
    if operator == 'exact':
        return '='

    return operator

class WhereNode(object):
    def __init__(self):
        self.column = None
        self.operator = None
        self.value = None
        self.output_field = None

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

    def set_leaf(self, column, operator, value, output_field=None):
        if operator == "iexact" and isinstance(output_field, AutoField):
            # When new instance is created, automatic primary key 'id' does not generate '_idx_iexact_id'.
            # As the primary key 'id' (AutoField) is integer and is always case insensitive,
            # we can deal with 'id_iexact=' query by using 'exact' rather than 'iexact'.
            operator = "exact"

        if operator == "isnull":
            operator = "exact"
            value = None

        self.column = column
        self.operator = convert_operator(operator)
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
        self.distinct = False
        self.order_by = []
        self.row_data = [] # For insert/updates
        self.where = None
        self.offset = self.limit = None

        self.annotations = []
        self.per_entity_annotations = []

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

    def set_distinct(self, distinct_fields):
        self.distinct = True
        if distinct_fields:
            self.columns = distinct_fields

    def add_order_by(self, column):
        self.order_by.append(column)

    def add_projected_column(self, column):
        if not self.columns:
            self.columns = [ column ]
        else:
            self.columns.append(column)

    def add_row(self, data):
        assert self.columns
        assert len(data) == len(self.columns)

        self.row_data.append(data)

    def set_where(self, where):
        assert where is None or isinstance(where, WhereNode)
        self.where = where

    def serialize(self):
        if not self.is_normalized:
            raise ValueError("You cannot serialize queries unless they are normalized")

        result = {}
        result["kind"] = self.kind
        result["table"] = self.tables[0]
        result["columns"] = self.columns
        result["distinct"] = self.distinct_fields
        result["order_by"] = self.order_by
        result["row_data"] = self.row_data

        where = []

        assert self.where.connector == 'OR'

        for node in self.where.children:
            assert node.connector == 'AND'

            query = {}
            for lookup in node.children:
                query[''.join(lookup.column, lookup.operator)] = lookup.value

            where.append(query)

        result["where"] = where

        return json.dumps(result)


def _extract_ordering_from_query_17(query):
    from djangae.db.backends.appengine.commands import log_once

    # Add any orderings
    if not query.default_ordering:
        result = list(query.order_by)
    else:
        result = list(query.order_by or query.get_meta().ordering or [])

    if query.extra_order_by:
        result.extend(query.extra_order_by)

    final = []

    opts = query.model._meta

    for col in result:
        if col.lstrip("-") == "pk":
            pk_col = query.model._meta.pk.column
            final.append("-" + pk_col if col.startswith("-") else pk_col)
        elif "__" in col:
            continue
        else:
            try:
                field = query.model._meta.get_field_by_name(col.lstrip("-"))[0]
                final.append("-" + field.column if col.startswith("-") else field.column)
            except FieldDoesNotExist:
                if col in query.extra_select:
                    # If the column is in the extra select we transform to the original
                    # column
                    try:
                        field = opts.get_field_by_name(query.extra_select[col][0])[0]
                        final.append("-" + field.column if col.startswith("-") else field.column)
                        continue
                    except FieldDoesNotExist:
                        # Just pass through to the exception below
                        pass

                available = opts.get_all_field_names()
                raise FieldError("Cannot resolve keyword %r into field. "
                    "Choices are: %s" % (col, ", ".join(available))
                )

    if len(final) != len(result):
        diff = set(result) - set(final)
        log_once(
            DJANGAE_LOG.warning if not on_production() else DJANGAE_LOG.debug,
            "The following orderings were ignored as cross-table and random orderings are not supported on the datastore: %s", diff
        )

    return final


def _extract_projected_columns_from_query_17(query):
    if query.select:
        result = []
        for x in query.select:
            if x.field is None:
                column = x.col.col[1]  # This is the column we are getting
            else:
                column = x.field.column

            result.append(column)
        return result
    else:
        # If the query uses defer()/only() then we need to process deferred. We have to get all deferred columns
        # for all (concrete) inherited models and then only include columns if they appear in that list
        deferred_columns = {}
        query.deferred_to_data(deferred_columns, query.deferred_to_columns_cb)
        inherited_db_tables = [x._meta.db_table for x in get_concrete_parents(query.model)]
        return list(chain(*[list(deferred_columns.get(x, [])) for x in inherited_db_tables]))


def _transform_query_17(connection, kind, query):
    if isinstance(query.where, EmptyWhere):
        # Empty where means return nothing!
        raise EmptyResultSet()

    ret = Query(query.model, kind)

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    # Extract the ordering of the query results
    for order_col in _extract_ordering_from_query_17(query):
        ret.add_order_by(order_col)

    # Extract any projected columns (values/values_list/only/defer)
    for projected_col in _extract_projected_columns_from_query_17(query):
        ret.add_projected_column(projected_col)

    # This must happen after extracting projected cols
    ret.set_distinct(list(query.distinct_fields))

    # Extract any query offsets and limits
    ret.offset = query.low_mark
    ret.limit = max((query.high_mark or 0) - query.low_mark, 0)

    output = WhereNode()
    output.connector = query.where.connector

    def walk_tree(source_node, new_parent):
        for child in source_node.children:
            new_node = WhereNode()

            if not getattr(child, "children", None):
                # Leaf
                lhs = child.lhs.output_field.column
                if child.rhs_is_direct_value():
                    rhs = child.rhs
                else:
                    rhs = child.lhs.output_field.get_db_prep_lookup(
                        child.lookup_name,
                        child.rhs,
                        connection,
                        prepared=True
                    )[0]

                new_node.set_leaf(
                    lhs,
                    child.lookup_name,
                    rhs,
                    child.lhs.output_field
                )

            else:
                new_node.connector = child.connector
                new_node.negated = child.negated
                walk_tree(child, new_node)

            new_parent.children.append(new_node)

    walk_tree(query.where, output)

    # If there no child nodes, just wipe out the where
    if not output.children:
        output = None

    ret.where = output

    return ret


def _extract_projected_columns_from_query_18(query):
    if query.select:
        result = []
        for x in query.select:
            if x.field is None:
                column = x.col.col[1]  # This is the column we are getting
            else:
                column = x.field.column

            result.append(column)
        return result
    else:
        # If the query uses defer()/only() then we need to process deferred. We have to get all deferred columns
        # for all (concrete) inherited models and then only include columns if they appear in that list
        deferred_columns = {}
        query.deferred_to_data(deferred_columns, query.get_loaded_field_names_cb)
        return list(chain(*[list(deferred_columns.get(x, [])) for x in get_concrete_parents(query.model)]))


def _transform_query_18(connection, kind, query):
    if isinstance(query.where, EmptyWhere):
        # Empty where means return nothing!
        raise EmptyResultSet()

    ret = Query(query.model, kind)

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    # Extract the ordering of the query results
    for order_col in _extract_ordering_from_query_17(query):
        ret.add_order_by(order_col)

    # Extract any projected columns (values/values_list/only/defer)
    for projected_col in _extract_projected_columns_from_query_18(query):
        ret.add_projected_column(projected_col)

    # This must happen after extracting projected cols
    ret.set_distinct(list(query.distinct_fields))

    # Extract any query offsets and limits
    ret.offset = query.low_mark
    ret.limit = max((query.high_mark or 0) - query.low_mark, 0)

    output = WhereNode()
    output.connector = query.where.connector

    def walk_tree(source_node, new_parent):
        for child in source_node.children:
            new_node = WhereNode()

            if not getattr(child, "children", None):
                # Leaf
                lhs = child.lhs.output_field.column
                if child.rhs_is_direct_value():
                    rhs = child.rhs
                else:
                    rhs = child.lhs.output_field.get_db_prep_lookup(
                        child.lookup_name,
                        child.rhs,
                        connection,
                        prepared=True
                    )[0]

                new_node.set_leaf(
                    lhs,
                    child.lookup_name,
                    rhs,
                    child.lhs.output_field
                )

            else:
                new_node.connector = child.connector
                new_node.negated = child.negated
                walk_tree(child, new_node)

            new_parent.children.append(new_node)

    walk_tree(query.where, output)

    # If there no child nodes, just wipe out the where
    if not output.children:
        output = None

    ret.where = output

    return ret


def _transform_query_19(kind, query):
    pass


_FACTORY = {
    (1, 7): _transform_query_17,
    (1, 8): _transform_query_18,
    (1, 9): _transform_query_19
}


def transform_query(connection, kind, query):
    return _FACTORY[django.VERSION[:2]](connection, kind, query)
