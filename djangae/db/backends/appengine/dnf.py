import copy
from itertools import  product
from django.db.models.sql.datastructures import EmptyResultSet
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

    # Explode IN filters into a series of 'OR statements to make life
    # easier later
    for child in node.children:
        if child.is_leaf and child.operator == "IN":
            new_children = []

            for value in child.value:
                new_node = WhereNode()
                new_node.operator = "="
                new_node.value = value
                new_node.column = child.column

                new_children.append(new_node)

            child.column = None
            child.operator = None
            child.connector = "OR"
            child.value = None
            child.children = new_children

    return node


def normalize_query(query):
    where = query.where

    # If there are no filters then this is already normalized
    if where is None:
        return query

    def walk_tree(where):
        preprocess_node(where)

        for child in where.children:
            if where.connector == "AND" and child.children and child.connector == 'AND' and not child.negated:
                where.children.remove(child)
                where.children.extend(child.children)
                walk_tree(where)
            elif child.connector == "AND" and len(child.children) == 1 and not child.negated:
                # Promote leaf nodes if they are the only child under an AND. Just for consistency
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


    def remove_empty_in(node):
        """
            Once we are normalized, if any of the branches filters
            on an empty list, we can remove that entire branch from the
            query. If this leaves no branches, then the result set is empty
        """

        # This is a bit ugly, but you try and do it more succinctly :)
        # We have the following possible situations for IN queries with an empty
        # value:

        # - Negated: One of the nodes in the and branch will always be true and is therefore
        #    unnecessary, we leave it alone though
        # - Not negated: The entire AND branch will always be false, so that branch can be removed
        #    if that was the last branch, then the queryset will be empty

        # Everything got wiped out!
        if node.connector == 'OR' and len(node.children) == 0:
            raise EmptyResultSet()

        for and_branch in node.children[:]:
            if and_branch.is_leaf and and_branch.operator == "IN" and not len(and_branch.value):
                node.children.remove(and_branch)

            if not node.children:
                raise EmptyResultSet()

    remove_empty_in(where)

    return query
