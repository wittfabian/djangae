import django
import json
import logging
import re

from itertools import chain, imap
from django.core.exceptions import FieldError
from django.db.models.fields import FieldDoesNotExist
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql.where import EmptyWhere
from django.db.models import AutoField

from django.db import NotSupportedError
from djangae.indexing import (
    special_indexes_for_column,
    REQUIRES_SPECIAL_INDEXES,
    add_special_index
)

from djangae.utils import on_production
from djangae.db.utils import (
    get_top_concrete_parent,
    get_concrete_parents,
    has_concrete_parents,
    get_field_from_column
)

from google.appengine.api import datastore


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
    elif operator == 'gt':
        return '>'
    elif operator == 'lt':
        return '<'
    elif operator == 'gte':
        return '>='
    elif operator == 'lte':
        return '<='

    return operator.upper()

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

        # The second part of this 'if' rules out foreign keys
        if output_field.primary_key and output_field.column == column:
            # If this is a primary key, we need to make sure that the value
            # we pass to the query is a datastore Key. We have to deal with IN queries here
            # because they aren't flattened until the DNF stage
            model = output_field.model
            if isinstance(value, (list, tuple)):
                value = [
                    datastore.Key.from_path(model._meta.db_table, x)
                    for x in value
                ]
            else:
                value = datastore.Key.from_path(model._meta.db_table, value)
            column = "__key__"

        if operator == "isnull":
            operator = "exact"
            value = None

        # Do any special index conversions necessary to perform this lookup
        if operator in REQUIRES_SPECIAL_INDEXES:
            indexer = REQUIRES_SPECIAL_INDEXES[operator]
            value = indexer.prep_value_for_query(value)
            column = indexer.indexed_column_name(column, value=value)
            operator = indexer.prep_query_operator(operator)

        self.column = column
        self.operator = convert_operator(operator)
        self.value = value

    def __iter__(self):
        for child in chain(*imap(iter, self.children)):
            yield child
        yield self


    def __repr__(self):
        if self.is_leaf:
            return "[%s%s%s]" % (self.column, self.operator, self.value)
        else:
            return "(%s:%s%s)" % (self.connector, "!" if self.negated else "", ",".join([repr(x) for x in self.children]))

    def __eq__(self, rhs):
        if self.is_leaf != rhs.is_leaf:
            return False

        if self.is_leaf:
            return self.column == rhs.column and self.value == rhs.value and self.operator == rhs.operator
        else:
            return self.connector == rhs.connector and self.children == rhs.children

    def __hash__(self):
        if self.is_leaf:
            return hash((self.column, self.value, self.operator))
        else:
            return hash((self.connector,) + tuple([hash(x) for x in self.children]))

class Query(object):
    def __init__(self, model, kind):
        assert kind in VALID_QUERY_KINDS

        self.model = model
        self.kind = kind

        self.projection_possible = True
        self.tables = []
        self.columns = None # None means all fields
        self.distinct = False
        self.order_by = []
        self.row_data = [] # For insert/updates
        self._where = None
        self.low_mark = self.high_mark = None

        self.annotations = []
        self.per_entity_annotations = []
        self.extra_selects = []

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

    def add_extra_select(self, column, lookup):
        if lookup.lower().startswith("select "):
            raise ValueError("SQL statements aren't supported with extra(select=)")

        # Boolean expression test
        bool_expr = "(?P<lhs>[a-zA-Z0-9_]+)\s?(?P<op>[=|>|<]{1,2})\s?(?P<rhs>[\w+|\']+)"

        # Operator expression test
        op_expr = "(?P<lhs>[a-zA-Z0-9_]+)\s?(?P<op>[+|-|/|*])\s?(?P<rhs>[\w+|\']+)"

        OP_LOOKUP = {
            "=": lambda x, y: x == y,
            "is": lambda x, y: x == y,
            "<": lambda x, y: x < y,
            ">": lambda x, y: x > y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "+": lambda x, y: x + y,
            "-": lambda x, y: x - y,
            "/": lambda x, y: x / y,
            "*": lambda x, y: x * y
        }

        for regex in (bool_expr, op_expr):
            match = re.match(bool_expr, lookup)
            if match:
                lhs = match.group('lhs')
                rhs = match.group('rhs')
                op = match.group('op').lower()
                if op in OP_LOOKUP:
                    self.extra_selects.append((column, (OP_LOOKUP[op], (lhs, rhs))))
                else:
                    raise ValueError("Unsupported operator")
                return

        # Assume literal
        self.extra_selects.append((column, (lambda x: x, [lookup])))

    def add_source_table(self, table):
        if table in self.tables:
            return

        self.tables.append(table)

    def set_distinct(self, distinct_fields):
        self.distinct = True
        if distinct_fields:
            for field in distinct_fields:
                self.add_projected_column(field)
        elif not self.columns:
            for field in self.model._meta.fields:
                self.add_projected_column(field.column)

    def add_order_by(self, column):
        self.order_by.append(column)

    def add_projected_column(self, column):
        if not self.projection_possible:
            # If we previously tried to add a column that couldn't be
            # projected, we don't try and add any more
            return

        field = get_field_from_column(self.model, column)

        if field is None:
            raise NotSupportedError("{} is not a valid column for the queried model. Did you try to join?".format(column))

        # We don't add primary key fields into the projection set
        if field.primary_key and field.column == column:
            return

        if field.db_type(self.connection) in ("bytes", "text", "list", "set"):
            DJANGAE_LOG.warn("Disabling projection query as %s is an unprojectable type", column)
            self.columns = None
            self.projection_possible = False
            return

        if not self.columns:
            self.columns = [ column ]
        else:
            self.columns.append(column)

    def add_row(self, data):
        assert self.columns
        assert len(data) == len(self.columns)

        self.row_data.append(data)

    @property
    def where(self):
        return self._where

    @where.setter
    def where(self, where):
        assert where is None or isinstance(where, WhereNode)
        self._where = where
        self._add_inheritence_filter()
        self._disable_projection_if_fields_used_in_equality_filter()

    def _disable_projection_if_fields_used_in_equality_filter(self):
        if not self._where or not self.columns:
            return

        equality_columns = set()

        def walk(node):
            if not node.is_leaf:
                for child in node.children:
                    walk(child)
            elif node.operator == "=" or node.operator == "IN":
                equality_columns.add(node.column)

        walk(self._where)

        if equality_columns and equality_columns.intersection(set(self.columns)):
            self.columns = None
            self.projection_possible = False

    def _add_inheritence_filter(self):
        """
            We support inheritence with polymodels. Whenever we set
            the 'where' on this query, we manipulate the tree so that
            the lookups are ANDed with a filter on 'class = db_table'
            and on inserts, we add the 'class' column if the model is part
            of an inheritance tree.

            We only do any of this if the model has concrete parents and isn't
            a proxy model
        """

        if has_concrete_parents(self.model) and not self.model._meta.proxy:
            new_filter = WhereNode()
            new_filter.column = 'class'
            new_filter.operator = '='
            new_filter.value = self.model._meta.db_table

            # We add this bare AND just to stay consistent with what Django does
            new_and = WhereNode()
            new_and.connector = 'AND'
            new_and.children = [ new_filter ]

            new_root = WhereNode()
            new_root.connector = 'AND'
            new_root.children = [ new_and, self._where ]
            self._where = new_root

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
            pk_col = "__key__"
            final.append("-" + pk_col if col.startswith("-") else pk_col)
        elif "__" in col:
            continue
        else:
            try:
                field = query.model._meta.get_field_by_name(col.lstrip("-"))[0]
                column = "__key__" if field.primary_key else field.column
                final.append("-" + column if col.startswith("-") else column)
            except FieldDoesNotExist:
                if col in query.extra_select:
                    # If the column is in the extra select we transform to the original
                    # column
                    try:
                        field = opts.get_field_by_name(query.extra_select[col][0])[0]
                        column = "__key__" if field.primary_key else field.column
                        final.append("-" + column if col.startswith("-") else column)
                        continue
                    except FieldDoesNotExist:
                        # Just pass through to the exception below
                        pass

                available = opts.get_all_field_names()
                raise FieldError("Cannot resolve keyword %r into field. "
                    "Choices are: %s" % (col, ", ".join(available))
                )

    # Reverse if not using standard ordering
    def swap(col):
        if col.startswith("-"):
            return col.lstrip("-")
        else:
            return "-{}".format(col)

    if not query.standard_ordering:
        final = [ swap(x) for x in final ]

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
    ret.connection = connection

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    # Extract the ordering of the query results
    for order_col in _extract_ordering_from_query_17(query):
        ret.add_order_by(order_col)

    # Extract any projected columns (values/values_list/only/defer)
    for projected_col in _extract_projected_columns_from_query_17(query):
        ret.add_projected_column(projected_col)

    # Add any extra selects
    for col, select in query.extra_select.items():
        ret.add_extra_select(col, select[0])

    # This must happen after extracting projected cols
    if query.distinct:
        ret.set_distinct(list(query.distinct_fields))

    # Extract any query offsets and limits
    ret.low_mark = query.low_mark
    ret.high_mark = query.high_mark

    output = WhereNode()
    output.connector = query.where.connector

    def walk_tree(source_node, new_parent):
        for child in source_node.children:
            new_node = WhereNode()

            if not getattr(child, "children", None):
                # Leaf
                lhs = child.lhs.target.column
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
    ret.connection = connection

    # Add the root concrete table as the source table
    root_table = get_top_concrete_parent(query.model)._meta.db_table
    ret.add_source_table(root_table)

    # Extract the ordering of the query results
    for order_col in _extract_ordering_from_query_17(query):
        ret.add_order_by(order_col)

    # Extract any projected columns (values/values_list/only/defer)
    for projected_col in _extract_projected_columns_from_query_18(query):
        ret.add_projected_column(projected_col)

    # Add any extra selects
    for col, select in query.extra_select.items():
        ret.add_extra_select(col, select[0])

    if query.distinct:
        # This must happen after extracting projected cols
        ret.set_distinct(list(query.distinct_fields))

    # Extract any query offsets and limits
    ret.low_mark = query.low_mark
    ret.high_mark = query.high_mark

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

def _determine_query_kind(query):
    from django.db.models.sql.aggregates import Count
    if query.aggregates:
        if None in query.aggregates and isinstance(query.aggregates[None], Count):
            return "COUNT"
        else:
            raise NotSupportedError("Unsupported aggregate: {}".format(query.aggregates))

    return "SELECT"

def transform_query(connection, query):
    return _FACTORY[django.VERSION[:2]](connection, _determine_query_kind(query), query)
