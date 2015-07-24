import copy
from itertools import  product
from django.db.models.sql.where import Constraint
from commands import parse_constraint, OPERATORS_MAP
from django.db.models.sql.datastructures import EmptyResultSet
from djangae.db.backends.appengine.dbapi import NotSupportedError

from google.appengine.api import datastore

try:
    from django.db.models import Lookup # Django 1.7+ uses lookup
except ImportError:
    # Fake lookup, so we can test using isinstance(node, Lookup) and this
    # will always return False on < 1.7
    class Lookup(object):
        pass


IMPOSSIBLE_FILTER = ('__key__', '<', datastore.Key.from_path('', 1))

class QueryContainsOR(Exception):
    pass

def check_for_inequalities(node, key=None, other=None):
    """
        Parses a query WHERE tree and logs which fields have inequalities.

        If the WHERE tree includes an OR connector, we throw QueryContainsOR for efficiency
        (because for our purposes we need to know quickly if the query contains an OR connector)
    """

    other = other or set()

    if hasattr(node, "children"):
        literals = [ x for x in node.children if not hasattr(x, "children") ]
        branches = [ x for x in node.children if hasattr(x, "children") ]

        if node.connector == 'OR':
            raise QueryContainsOR

        for literal in literals:
            # Django 1.7+ have a lhs attribute which stores column info, django 1.6 doesn't
            field = literal.lhs.output_field if hasattr(literal, "lhs") else literal[0].field
            field_name = field.column if field else literal[0].col

            # Again, Django 1.7+ has lookup_name, 1.6 doesn't
            lookup = literal.lookup_name if hasattr(literal, "lookup_name") else literal[1]

            if node.negated and lookup == "exact" and (field and field.primary_key):
                key = field_name
            elif ((node.negated and lookup == "exact") or (lookup in ("gt", "gte", "lt", "lte"))) and not (field and field.primary_key):
                other.add(field_name)

        for branch in branches:
            k, o = check_for_inequalities(branch, key, other)
            if k:
                key = k
            other.update(o)

    return key, other

def should_exclude_pks_in_memory(query, ordering):
    """
        We try to let the datastore do as much of the work as possible, however, there are times
        when we can actually support two inequalities in a query, if one of them is on the key. Also,
        we can support an inequality on a key, and an ordering by something else. This code literally
        returns True in those cases, in which case the dnf parsing will keep track of the excluded PKs
        and remove them from the tree, otherwise, it will add them to the tree as a > && < combo as
        normal.
    """
    try:
        key_inequality, other_inequalities = check_for_inequalities(query)
    except QueryContainsOR:
        return False

    if len(other_inequalities) == 1 or (
        key_inequality and not other_inequalities and ordering and ordering[0].lstrip("-") != key_inequality):
        return True
    else:
        return False

def process_literal(node, is_pk_filter, excluded_pks, filtered_columns=None, negated=False):
    column, op, value = node[1]
    if filtered_columns is not None:
        assert isinstance(filtered_columns, set)
        filtered_columns.add(column)
    if op == 'in':  # Explode INs into OR
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("IN queries must be supplied a list of values")
        if negated:
            if len(value) == 0:
                return None, filtered_columns

            lits = []
            for x in value:
                lits.append(('LIT', (column, '>', x)))
                lits.append(('LIT', (column, '<', x)))
            return ('OR', lits), filtered_columns
        else:
            if not value:
                # Add an impossible filter when someone queries on an empty list, which should never return anything for
                # this branch. We can't just raise an EmptyResultSet because another branch might return something
                return ('AND', [('LIT', IMPOSSIBLE_FILTER)]), filtered_columns
            return ('OR', [('LIT', (column, '=', x)) for x in value]), filtered_columns
    elif op == "isnull":
        if negated:
            value = not value
            negated = not negated

        if not value:
            lits = []
            lits.append(('LIT', (column, '>', None)))
            lits.append(('LIT', (column, '<', None)))
            return ('OR', lits), filtered_columns
        else:
            op = "exact"
            value = None
    elif op == "range":
        lits = []
        if not negated:
            lits.append(('LIT', (column, '>=', value[0])))
            lits.append(('LIT', (column, '<=', value[1])))
            return ('AND', lits), filtered_columns
        else:
            lits.append(('LIT', (column, '<', value[0])))
            lits.append(('LIT', (column, '>', value[1])))
            return ('OR', lits), filtered_columns

    if not OPERATORS_MAP.get(op):
        raise NotSupportedError("Unsupported operator %s" % op)
    _op = OPERATORS_MAP[op]

    if negated and _op == '=':  # Explode
        if is_pk_filter and excluded_pks is not None: #Excluded pks is a set() if we should be using it
            excluded_pks.add(value)
            return None, filtered_columns

        return ('OR', [('LIT', (column, '>', value)), ('LIT', (column, '<', value))]), filtered_columns
    return ('LIT', (column, _op, value)), filtered_columns


def process_node(node, connection, negated=False):
    if isinstance(node, Lookup):
        field = node.lhs.output_field
        is_pk = field and field.primary_key
        return ('LIT', parse_constraint(node, connection, negated)), negated, is_pk
    elif isinstance(node, tuple) and isinstance(node[0], Constraint):
        field = node[0].field
        is_pk = field and field.primary_key
        return ('LIT', parse_constraint(node, connection, negated)), negated, is_pk
    if isinstance(node, tuple):
        return node, negated, False

    if node.negated:
        negated = True


        # This is a little crazy, but bear with me...
        # If you run a query like this:  filter(thing=1).exclude(field1="test") where field1 is
        # null-able you'll end up with a negated branch in the where tree which is:

        #           AND (negated)
        #          /            \
        #   field1="test"   field1__isnull=False

        # This is because on SQL, field1 != "test" won't give back rows where field1 is null, so
        # django has to include the negated isnull=False as well in order to get back the null rows
        # as well.  On App Engine though None is just a value, not the lack of a value, so it's
        # enough to just have the first branch in the negated node and in fact, if you try to use
        # the above tree, it will result in looking for:
        #  field1 < "test" and field1 > "test" and field1__isnull=True
        # which returns the wrong result (it'll return when field1 == None only)

        if node.connector == 'AND':
            # If the connector is 'AND'
            field_equalities = {}

            def get_op(constraint_or_lookup):
                # <= 1.6 child is a tuple, else it's a lookup
                return constraint_or_lookup[1] if isinstance(constraint_or_lookup, tuple) else constraint_or_lookup.lookup_name

            def get_lhs_col(constraint_or_lookup):
                # <= 1.6 child is a tuple, else it's a lookup
                return constraint_or_lookup[0].col if isinstance(constraint_or_lookup, tuple) else constraint_or_lookup.lhs.target.column

            # Look and see if we have an exact and isnull on the same field
            for child in node.children:
                op = get_op(child)
                column = get_lhs_col(child)
                if op in ('exact', 'isnull'):
                    field_equalities.setdefault(column, []).append(op)

            # If so, remove the isnull
            for field, equalities in field_equalities.iteritems():
                if sorted(equalities) != [ 'exact', 'isnull' ]:
                    continue

                # If we have more than one equality and one of them is isnull, then remove it
                node.children = [ x for x in node.children if get_lhs_col(x) != field or get_op(x) != 'isnull' ]


    return (node.connector, [child for child in node.children]), negated, False


def parse_dnf(node, connection, ordering=None):
    should_in_memory_exclude = should_exclude_pks_in_memory(node, ordering)

    tree, filtered_columns, excluded_pks = parse_tree(
        node, connection,
        excluded_pks = set() if should_in_memory_exclude else None
    )

    if not should_exclude_pks_in_memory:
        assert excluded_pks is None

    if tree:
        tree = tripled(tree)


    if tree and tree[0] != 'OR':
        tree = ('OR', [tree])


    # Filter out impossible branches of the where, if that then results in an empty tree then
    # raise an EmptyResultSet, otherwise replace the tree with the now simpler query
    if tree:
        final = []
        for and_branch in tree[-1]:
            if and_branch[0] == 'LIT' and and_branch[-1] == IMPOSSIBLE_FILTER:
                continue
            elif and_branch[0] == 'AND' and IMPOSSIBLE_FILTER in [x[-1] for x in and_branch[-1] ]:
                continue

            final.append(and_branch)
        if not final:
            raise EmptyResultSet()
        else:
            tree = (tree[0], final)

    # If there are more than 30 filters, and not all filters are PK filters
    if tree and len(tree[-1]) > 30:
        for and_branch in tree[-1]:
            if and_branch[0] == 'LIT':
                and_branch = [and_branch]
            for lit in and_branch[-1] if and_branch[0] == 'AND' else and_branch:  # Go through each literal tuple
                if isinstance(lit[-1], datastore.Key) or isinstance(lit[-1][-1], datastore.Key):  # If the value is a key, then break the loop
                    break
            else:
                # If we didn't find a literal with a datastore Key, then raise unsupported
                raise NotSupportedError("The datastore doesn't support this query, more than 30 filters were needed")

    return tree, filtered_columns, excluded_pks or set()


def parse_tree(node, connection, filtered_columns=None, excluded_pks=None, negated=False):
    """
        Takes a django tree and parses all the nodes returning a new
        tree in the correct format for expansion
    """
    filtered_columns = filtered_columns or set()

    node, negated, is_pk_filter = process_node(node, connection, negated=negated)

    if node[0] in ['AND', 'OR']:
        new_children = []
        for child in node[1]:
            parsed_node, _columns, excluded_pks = parse_tree(child, connection, filtered_columns, excluded_pks, negated)
            if parsed_node:
                new_children.append(parsed_node)

            for col in _columns:
                filtered_columns.add(col)

        if not new_children:
            return None, filtered_columns, excluded_pks

        if len(new_children) == 1:
            return new_children[0], filtered_columns, excluded_pks
        return (node[0], new_children), filtered_columns, excluded_pks
    if node[0] == 'LIT':
        parsed_lit, _columns = process_literal(node, is_pk_filter, excluded_pks, filtered_columns=filtered_columns, negated=negated)

        for col in _columns:
            filtered_columns.add(col)
        return parsed_lit, filtered_columns, excluded_pks


def tripled(node):
    """
        Applies DNF to a parsed tree
    """
    if node[0] == 'LIT':
        return node
    elif node[0] == 'AND':
        new_children = []
        is_reduction = False
        for child in node[1]:
            if child[0] == 'AND':
                # There is a reduction
                is_reduction = True
                for x in child[1]:
                    # append directly
                    new_children.append(x)
            else:
                new_children.append(child)
        if is_reduction:
            return tripled(('AND', new_children))
        else:
            is_or = False
            children = []
            for child in new_children:
                children.append(tripled(child))
            product_pipe = []
            for child in children:
                # It is known at this point that none of these children can be
                # AND nodes because they would have been reduced previously
                if child[0] == 'OR':
                    is_or = True
                    lits = []
                    for x in child[1]:
                        if x[0] == 'LIT':
                            lits.append(x)
                        else:
                            lits.append(x[1])
                    product_pipe.append(lits)
                elif child[0] == 'LIT':
                    product_pipe.append([child])
            if is_or == False:
                # If there are only literals then there is nothing we can do
                return 'AND', children
            else:
                # If there is an OR then we can do crazy product
                def flatten(container):
                    """
                        Only flattens nested lists and ignores tuples
                    """
                    for i in container:
                        if isinstance(i, list):
                            for j in flatten(i):
                                yield j
                        else:
                            yield i
                return 'OR', [('AND', list(flatten(x))) for x in product(*product_pipe)]
    elif node[0] == 'OR':
        children = []
        for child in node[1]:
            _proc = tripled(child)
            if _proc[0] == 'OR':
                for child in _proc[1]:
                    children.append(child)
            else:
                children.append(_proc)
        return 'OR', children


from djangae.db.backends.appengine.query import WhereNode

def preprocess_node(node):
    # Explode inequalities otherwise things get crazy
    if node.negated and len(node.children) == 1 and node.children[0].operator == "=":
        only_grandchild = node.children[0]

        lhs, rhs = WhereNode(), WhereNode()
        lhs.column = rhs.column = only_grandchild.column
        lhs.value = rhs.value = only_grandchild.value
        lhs.operator = "<"
        rhs.operator = ">"

        node.children = [ lhs, rhs ]
        node.connector = "OR"
        node.negated = False

    if not node.negated:
        for child in node.children:
            if child.is_leaf and child.operator == "in":
                new_children = []

                for value in node.children[0].value:
                    new_node = WhereNode()
                    new_node.operator = "="
                    new_node.value = value
                    new_node.column = node.children[0].column

                    new_children.append(new_node)

                child.column = None
                child.operator = None
                child.connector = "OR"
                child.value = None
                child.children = new_children

    return node


def normalize_query(query):
    where = query.where

    def walk_tree(where):
        for child in where.children:
            child = preprocess_node(child)

            if where.connector == "AND" and child.children and child.connector == 'AND' and not child.negated:
                where.children.remove(child)
                where.children.extend(child.children)
                walk_tree(where)
            elif len(child.children) > 1 and child.connector == 'AND' and child.negated:
                new_grandchildren = []
                for grandchild in child.children:
                    new_node = WhereNode()
                    new_node.negated = True
                    new_node.children = [ grandchild ]
                    new_grandchildren.append(new_node)
                child.children = new_grandchildren
                child.connector = 'OR'
                walk_tree(where)
            else:
                walk_tree(child)

        if where.connector == 'AND' and any([x.connector == 'OR' for x in where.children]):
            # ANDs should have been taken care of!
            assert not any([x.connector == 'AND' and not x.is_leaf for x in where.children ])

            product_list = []
            for child in where.children:
                if child.connector == 'OR':
                    product_list.append(child.children)
                else:
                    product_list.append([child])

            producted = product(*product_list)

            new_children = []
            for branch in producted:
                new_and = WhereNode()
                new_and.connector = 'AND'
                new_and.children = list(copy.deepcopy(branch))
                new_children.append(new_and)

            where.connector = 'OR'
            where.children = list(set(new_children))
            walk_tree(where)

        elif where.connector == 'OR':
            new_children = []
            for child in where.children:
                if child.connector == 'OR':
                    new_children.extend(child.children)
                else:
                    new_children.append(child)
            where.children = list(set(new_children))

    walk_tree(where)

    if where.connector != 'OR':
        new_node = WhereNode()
        new_node.connector = 'OR'
        new_node.children = [ where ]
        query.where = new_node

    return query
