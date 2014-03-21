import logging
import itertools
import warnings

from google.appengine.api import datastore
from google.appengine.api.datastore_types import Key

from django.core.cache import cache

from django.db.models.sql.where import AND
from djangae.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES, add_special_index


OPERATORS_MAP = {
    'exact': '=',
    'gt': '>',
    'gte': '>=',
    'lt': '<',
    'lte': '<=',

    # The following operators are supported with special code below.
    'isnull': None,
    'in': None,
    'startswith': None,
    'range': None,
    'year': None,
    'gt_and_lt': None, #Special case inequality combined filter
    'iexact': None
}

def get_field_from_column(model, column):
    #FIXME: memoize this!
    for field in model._meta.fields:
        if field.column == column:
            return field
    return None

class SelectCommand(object):
    def __init__(self, connection, model, queried_fields, where, is_count=False, ordering=[], projection_enabled=True):
        assert isinstance(is_count, bool)
        assert isinstance(ordering, list)
        assert isinstance(projection_enabled, bool)

        self.connection = connection
        self.pk_col = model._meta.pk.column
        self.model = model
        self.queried_fields = queried_fields
        self.is_count = is_count
        self.keys_only = False #FIXME: This should be used where possible
        self.included_pks = []
        self.excluded_pks = []
        self.has_inequality_filter = False
        self.all_filters = []
        self.results = None
        self.ordering = ordering

        if not self.queried_fields:
            self.queried_fields = [ x.column for x in model._meta.fields ]

        projection_fields = []
        if projection_enabled:
            for field in self.queried_fields:
                #We don't include the primary key in projection queries...
                if field == self.pk_col:
                    continue

                #Text and byte fields aren't indexed, so we can't do a
                #projection query
                f = get_field_from_column(model, field)
                assert f #If this happens, we have a cross-table select going on! #FIXME
                db_type = f.db_type(connection)

                if db_type in ("bytes", "text"):
                    projection_fields = []
                    break

                projection_fields.append(field)

        self.projection = list(set(projection_fields)) or None
        if model._meta.parents:
            self.projection = None

        self.where = self.parse_where_and_check_projection(where)

        try:
            #If the PK was queried, we switch it in our queried
            #fields store with __key__
            pk_index = self.queried_fields.index(self.pk_col)
            self.queried_fields[pk_index] = "__key__"

            #If the only field queried was the key, then we can do a keys_only
            #query
            self.keys_only = len(self.queried_fields) == 1
        except ValueError:
            pass

    def parse_where_and_check_projection(self, where, negated=False):
        result = []

        if where.negated:
            negated = not negated

        if not negated and where.connector != AND:
            raise DatabaseError("Only AND filters are supported")

        for child in where.children:
            if isinstance(child, tuple):
                constraint, op, annotation, value = child

                #Disable projection if it's not supported
                if self.projection and constraint.col in self.projection:
                    if op in ("exact", "in", "isnull"):
                        #If we are projecting, but we are doing an
                        #equality filter on one of the columns, then we
                        #can't project
                        self.projection = None

                if negated:
                    if op in ("exact", "in") and constraint.field.primary_key:
                        self.excluded_pks.append(value)
                    #else: FIXME when excluded_pks is handled, we can put the
                    #next section in an else block
                    if op == "exact":
                        if self.has_inequality_filter:
                            raise RuntimeError("You can only specify one inequality filter per query")

                        col = constraint.col
                        result.append((col, "gt_and_lt", value))
                        self.has_inequality_filter = True
                    else:
                        raise RuntimeError("Unsupported negated lookup: " + op)
                else:
                    if op in ("exact", "in") and constraint.field.primary_key:
                        if isinstance(value, (list, tuple)):
                            self.included_pks.extend(list(value))
                        else:
                            self.included_pks.append(value)
                    #else: FIXME when included_pks is handled, we can put the
                    #next section in an else block
                    col = constraint.col
                    result.append((col, op, value))
            else:
                result.extend(self.parse_where_and_check_projection(child, negated))
        return result

    def execute(self):
        combined_filters = []

        inheritance_root = self.model

        concrete_parents = [ x for x in self.model._meta.parents if not x._meta.abstract]

        if concrete_parents:
            for parent in self.model._meta.get_parent_list():
                if not parent._meta.parents:
                    #If this is the top parent, override the db_table
                    inheritance_root = parent

        query = datastore.Query(
            inheritance_root._meta.db_table,
            projection=self.projection
        )

        #Only filter on class if we have some non-abstract parents
        if concrete_parents and not self.model._meta.proxy:
            query["class ="] = self.model._meta.db_table

        logging.info("Select query: {0}, {1}".format(self.model.__name__, self.where))

        for column, op, value in self.where:
            def clean_pk_value(_value):
                if isinstance(_value, basestring):
                    _value = _value[:500]
                    left = _value[500:]
                    if left:
                        warnings.warn("Truncating primary key"
                            " that is over 500 characters. THIS IS AN ERROR IN YOUR PROGRAM.",
                            RuntimeWarning
                        )
                    _value = Key.from_path(inheritance_root._meta.db_table, _value)
                else:
                    _value = Key.from_path(inheritance_root._meta.db_table, _value)

                return _value

            if column == self.pk_col:
                column = "__key__"

                if isinstance(value, (list, tuple)):
                    value = [ clean_pk_value(x) for x in value]
                else:
                    value = clean_pk_value(value)

            final_op = OPERATORS_MAP.get(op)
            if final_op is None:
                if op in REQUIRES_SPECIAL_INDEXES:
                    add_special_index(self.model, column, op) #Add the index if we can (e.g. on dev_appserver)

                    if op not in special_indexes_for_column(self.model, column):
                        raise RuntimeError("There is a missing index in your djangaeidx.yaml - \n\n{0}:\n\t{1}: [{2}]".format(
                            self.model, column, op)
                        )

                    indexer = REQUIRES_SPECIAL_INDEXES[op]
                    column = indexer.indexed_column_name(column)
                    value = indexer.prep_value_for_query(value)
                    query["%s =" % column] = value
                else:
                    if op == "in":
                        combined_filters.append((column, op, value))
                    elif op == "gt_and_lt":
                        combined_filters.append((column, op, value))
                    elif op == "isnull":
                        query["%s =" % column] = None
                    else:
                        raise NotImplementedError("Unimplemented operator {0}".format(op))
            else:
                query["%s %s" % (column, final_op)] = value

        ##Apply any ordering
        if self.ordering:
            ordering = [
                (x.lstrip("-"), datastore.Query.DESCENDING if x.startswith("-") else datastore.Query.ASCENDING)
                for x in self.ordering
            ]
            query.Order(*ordering)

        if combined_filters:
            queries = [ query ]
            for column, op, value in combined_filters:
                new_queries = []
                for query in queries:
                    if op == "in":
                        for val in value:
                            new_query = datastore.Query(self.model._meta.db_table)
                            new_query.update(query)
                            new_query["%s =" % column] = val
                            new_queries.append(new_query)
                    elif op == "gt_and_lt":
                        for tmp_op in ("<", ">"):
                            new_query = datastore.Query(self.model._meta.db_table)
                            new_query.update(query)
                            new_query["%s %s" % (column, tmp_op)] = value
                            new_queries.append(new_query)
                queries = new_queries

            query = datastore.MultiQuery(queries, [])

        #print query
        self.query = query
        self.results = None
        self.query_done = False
        self.aggregate_type = "count" if self.is_count else None
        self._do_fetch()

    def _do_fetch(self):
        assert not self.results

        if isinstance(self.query, datastore.MultiQuery):
            self.results = self._run_query(aggregate_type=self.aggregate_type)
            self.query_done = True
        else:
            #Try and get the entity from the cache, this is to work around HRD issues
            #and boost performance!
            entity_from_cache = None
            if self.all_filters and self.model:
                #Get all the exact filters
                exact_filters = [ x for x in self.all_filters if x[1] == "=" ]
                lookup = { x[0]:x[2] for x in exact_filters }

                unique_combinations = get_uniques_from_model(self.model)
                for fields in unique_combinations:
                    final_key = []
                    for field in fields:
                        if field in lookup:
                            final_key.append((field, lookup[field]))
                            continue
                        else:
                            break
                    else:
                        #We've found a unique combination!
                        unique_key = generate_unique_key(self.model, final_key)
                        entity_from_cache = get_entity_from_cache(unique_key)

            if entity_from_cache is None:
                self.results = self._run_query(aggregate_type=self.aggregate_type)
            else:
                self.results = [ entity_from_cache ]

    def _run_query(self, limit=None, start=None, aggregate_type=None):
        if aggregate_type is None:
            return self.query.Run(limit=limit, start=start)
        elif self.aggregate_type == "count":
            return self.query.Count(limit=limit, start=start)
        else:
            raise RuntimeError("Unsupported query type")

class FlushCommand(object):
    """
        sql_flush returns the SQL statements to flush the database,
        which are then executed by cursor.execute()

        We instead return a list of FlushCommands which are called by
        our cursor.execute
    """
    def __init__(self, table):
        self.table = table

    def execute(self):
        table = self.table
        query = datastore.Query(table, keys_only=True)
        while query.Count():
            datastore.Delete(query.Run())

        cache.clear()

class InsertCommand(object):
    def __init__(self, model, entities):
        self.entities = entities
        self.model = model

class DeleteCommand(object):
    def __init__(self, connection, model, where):
        self.select = SelectCommand(connection, model, [model._meta.pk.column], where=where, is_count=False)

    def execute(self):
        self.select.execute()
        datastore.Delete(self.select.results)
        #FIXME: Remove from the cache

class UpdateCommand(object):
    def __init__(self, connection, model, values, where):
        self.model = model
        self.select = SelectCommand(connection, model, [], where=where, is_count=False, projection_enabled=False)
        self.values = values
        self.connection = connection

    def execute(self):
        from .base import get_prepared_db_value, MockInstance
        from .base import cache_entity

        self.select.execute()

        results = self.select.results
        entities = []
        i = 0
        for result in results:
            i += 1
            for field, param, value in self.values:
                result[field.column] = get_prepared_db_value(self.connection, MockInstance(field, value), field)

                #Add special indexed fields
                for index in special_indexes_for_column(self.model, field.column):
                    indexer = REQUIRES_SPECIAL_INDEXES[index]
                    result[indexer.indexed_column_name(field.column)] = indexer.prep_value_for_database(value)

            entities.append(result)

        returned_ids = datastore.Put(entities)

        model = self.select.model

        #Now cache them, temporarily to help avoid consistency errors
        for key, entity in itertools.izip(returned_ids, entities):
            pk_column = model._meta.pk.column

            #If there are parent models, search the parents for the
            #first primary key which isn't a relation field
            for parent in model._meta.parents.keys():
                if not parent._meta.pk.rel:
                    pk_column = parent._meta.pk.column

            entity[pk_column] = key.id_or_name()
            cache_entity(model, entity)

        return i
