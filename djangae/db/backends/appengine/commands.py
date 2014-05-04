#STANDARD LIB
from datetime import datetime
import itertools
import logging

#LIBRARIES
from django.core.cache import cache
from django.db.backends.mysql.compiler import SQLCompiler
from django.db import IntegrityError
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql.where import AND
from django import dispatch
from google.appengine.api import datastore
from google.appengine.api.datastore_types import Key
from google.appengine.ext import db

#DJANGAE
from djangae.db.caching import cache_entity
from djangae.db.exceptions import NotSupportedError, CouldBeSupportedError
from djangae.db.utils import (
    django_instance_to_entity,
    get_datastore_kind,
    get_prepared_db_value,
    MockInstance,
    normalise_field_value,
)
from djangae.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES, add_special_index


entity_pre_update = dispatch.Signal(providing_args=["sender", "entity"])
entity_post_update = dispatch.Signal(providing_args=["sender", "entity"])
entity_post_insert = dispatch.Signal(providing_args=["sender", "entity"])
entity_deleted = dispatch.Signal(providing_args=["sender", "entity"])
get_pre_execute = dispatch.Signal(providing_args=["sender", "key"])
query_pre_execute = dispatch.Signal(providing_args=["sender", "query", "aggregate"])

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
    'iexact': None,
}


def get_field_from_column(model, column):
    #FIXME: memoize this
    for field in model._meta.fields:
        if field.column == column:
            return field
    return None

def field_conv_year_only(value):
    value = ensure_datetime(value)
    return datetime(value.year, 1, 1, 0, 0)

def field_conv_month_only(value):
    value = ensure_datetime(value)
    return datetime(value.year, value.month, 1, 0, 0)

def field_conv_day_only(value):
    value = ensure_datetime(value)
    return datetime(value.year, value.month, value.day, 0, 0)

def ensure_datetime(value):
    """ Painfully, sometimes the Datastore returns dates as datetime objects, and sometimes
        it returns them as unix timestamps in microseconds!!
    """
    if isinstance(value, long):
        return datetime.fromtimestamp(value / 1000000)
    return value



FILTER_CMP_FUNCTION_MAP = {
    'exact': lambda a, b: a == b,
    'iexact': lambda a, b: a.lower() == b.lower(),
    'gt': lambda a, b: a > b,
    'lt': lambda a, b: a < b,
    'gte': lambda a, b: a >= b,
    'lte': lambda a, b: a <= b,
    'isnull': lambda a, b: (b and (a is None)) or (a is not None),
    'in': lambda a, b: a in b,
    'startswith': lambda a, b: a.startswith(b),
    'range': lambda a, b: b[0] < a < b[1], #I'm assuming that b is a tuple
    'year': lambda a, b: field_conv_year_only(a) == b,
}


class SelectCommand(object):
    def __init__(self, connection, query, keys_only=False, all_fields=False):
        self.original_query = query

        opts = query.get_meta()
        if not query.default_ordering:
            self.ordering = query.order_by
        else:
            self.ordering = query.order_by or opts.ordering

        self.distinct_values = set()
        self.distinct_on_field = None
        self.distinct_field_convertor = None
        self.queried_fields = []

        if keys_only:
            self.queried_fields = [ opts.pk.column ]
        elif not all_fields:
            for x in query.select:
                if isinstance(x, tuple):
                    #Django < 1.6 compatibility
                    self.queried_fields.append(x[1])
                else:
                    self.queried_fields.append(x.col[1])

                    if x.lookup_type == 'year':
                        assert self.distinct_on_field is None
                        self.distinct_on_field = x.col[1]
                        self.distinct_field_convertor = field_conv_year_only
                    elif x.lookup_type == 'month':
                        assert self.distinct_on_field is None
                        self.distinct_on_field = x.col[1]
                        self.distinct_field_convertor = field_conv_month_only
                    elif x.lookup_type == 'day':
                        assert self.distinct_on_field is None
                        self.distinct_on_field = x.col[1]
                        self.distinct_field_convertor = field_conv_day_only
                    else:
                        raise NotSupportedError("Unhandled lookup type: {0}".format(x.lookup_type))


        #Projection queries don't return results unless all projected fields are
        #indexed on the model. This means if you add a field, and all fields on the model
        #are projectable, you will never get any results until you've resaved all of them.

        #Because it's not possible to detect this situation, we only try a projection query if a
        #subset of fields was specified (e.g. values_list('bananas')) which makes the behaviour a
        #bit more predictable. It would be nice at some point to add some kind of force_projection()
        #thing on a queryset that would do this whenever possible, but that's for the future, maybe.
        try_projection = bool(self.queried_fields)

        if not self.queried_fields:
            self.queried_fields = [ x.column for x in opts.fields ]

        self.connection = connection
        self.pk_col = opts.pk.column
        self.model = query.model
        self.is_count = query.aggregates
        self.keys_only = False #FIXME: This should be used where possible
        self.included_pks = []
        self.excluded_pks = []
        self.has_inequality_filter = False
        self.all_filters = []
        self.results = None
        self.extra_select = query.extra_select
        self.gae_query = None

        self._set_db_table()
        self._validate_query_is_possible(query)

        projection_fields = []

        if try_projection:
            for field in self.queried_fields:
                #We don't include the primary key in projection queries...
                if field == self.pk_col:
                    continue

                #Text and byte fields aren't indexed, so we can't do a
                #projection query
                f = get_field_from_column(self.model, field)
                if not f:
                    raise NotImplementedError("Attemping a cross-table select. Maybe? #FIXME")
                assert f #If this happens, we have a cross-table select going on! #FIXME
                db_type = f.db_type(connection)

                if db_type in ("bytes", "text"):
                    projection_fields = []
                    break

                projection_fields.append(field)

        self.projection = list(set(projection_fields)) or None
        if opts.parents:
            self.projection = None

        self.where = self.parse_where_and_check_projection(query.where)

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
        """ recursively parse the where tree and return a list of tuples of
            (column, match_type, value), e.g. ('name', 'exact', 'John').
        """
        result = []

        if where.negated:
            negated = not negated

        if negated and where.connector != AND:
            raise DatabaseError("Only AND filters are supported for negated queries")

        for child in where.children:
            if isinstance(child, tuple):
                constraint, op, annotation, value = child
                if isinstance(value, (list, tuple)):
                    value = [ self.connection.ops.prep_lookup_value(self.model, x, constraint.field) for x in value]
                else:
                    value = self.connection.ops.prep_lookup_value(self.model, value, constraint.field)

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
                    if constraint.field.primary_key:
                        if (value is None and op == "exact") or (op == "isnull" and value):
                            #If we are looking for a primary key that is None, then we always
                            #just return nothing
                            raise EmptyResultSet()

                        elif op in ("exact", "in"):
                            if isinstance(value, (list, tuple)):
                                self.included_pks.extend(list(value))
                            else:
                                self.included_pks.append(value)
                        else:
                            col = constraint.col
                            result.append((col, op, value))
                    else:
                        col = constraint.col
                        result.append((col, op, value))
            else:
                result.extend(self.parse_where_and_check_projection(child, negated))

        return result

    def execute(self):
        if not self.included_pks:
            self.gae_query = self._build_gae_query()
        self.results = None
        self.query_done = False
        self.aggregate_type = "count" if self.is_count else None
        self._do_fetch()

    def _log(self):
        templ = """
            SELECT {0} FROM {1} WHERE {2}
        """

        select = ", ".join(self.projection) if self.projection else "*"
        if self.aggregate_type:
            select = "COUNT(*)"

        where = str(self.gae_query)

        final = templ.format(
            select,
            get_datastore_kind(self.model),
            where
        ).strip()

        tmp = SQLCompiler(self.original_query, self.connection, None)
        try:
            sql, params = tmp.as_sql()
            print(sql % params)
        except:
            print("Unable to print MySQL equivalent - empty query")
        print(final)

    def _set_db_table(self):
        """ Work out which Datstore kind we should actually be querying. This allows for poly
            models, i.e. non-abstract parent models which we support by storing all fields for
            both the parent model and its child models on the parent table.
        """
        inheritance_root = self.model
        concrete_parents = [ x for x in self.model._meta.parents if not x._meta.abstract]
        if concrete_parents:
            for parent in self.model._meta.get_parent_list():
                if not parent._meta.parents:
                    #If this is the top parent, override the db_table
                    inheritance_root = parent
        self.db_table = inheritance_root._meta.db_table
        self.have_concrete_parent_models = bool(concrete_parents)

    def _validate_query_is_possible(self, query):
        """ Given the *django* query, check the following:
            - The query only has one inequality filter
            - The query does no joins
            - The query ordering is compatible with the filters
        """
        #Check for joins
        if query.count_active_tables() > 1:
            if self.have_concrete_parent_models:
                raise CouldBeSupportedError(
                    "Querying for a poly model. This could be supported in some cases, i.e. when "
                    "it's a simple query. If it's a poly model with JOINs in the filters then we "
                    "can't support it."
                )
            raise NotSupportedError("""
                The appengine database connector does not support JOINs. The requested join map follows\n
                %s
            """ % query.join_map)

        if query.aggregates:
            if query.aggregates.keys() == [ None ]:
                if query.aggregates[None].col != "*":
                    raise NotSupportedError("Counting anything other than '*' is not supported")
            else:
                raise NotSupportedError("Unsupported aggregate query")

        #This is a hack! Django < 1.7 sets an extra_select of a = 1 in has_results. In 1.7 this has
        #been moved to the compiler.
        if query.extra_select and query.extra_select != {'a': (u'1', [])}:
            raise CouldBeSupportedError("The appengine connector currently doesn't support extra_select, it can be implemented though")

    def _build_gae_query(self):
        """ Build and return the Datstore Query object. """
        combined_filters = []
        query = datastore.Query(
            self.db_table,
            projection=self.projection
        )

        #Only filter on class if we have some non-abstract parents
        if self.have_concrete_parent_models and not self.model._meta.proxy:
            query["class ="] = self.model._meta.db_table

        logging.info("Select query: {0}, {1}".format(self.model.__name__, self.where))

        for column, op, value in self.where:
            if column == self.pk_col:
                column = "__key__"

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
                    elif op == "startswith":
                        #You can emulate starts with by adding the last unicode char
                        #to the value, then doing <=. Genius.
                        query["%s >=" % column] = value
                        if isinstance(value, str):
                            value = value.decode("utf-8")
                        value += u'\ufffd'
                        query["%s <=" % column] = value
                    else:
                        raise NotImplementedError("Unimplemented operator {0}".format(op))
            else:
                query["%s %s" % (column, final_op)] = value

        ordering = []
        for order in self.ordering:
            if isinstance(order, int):
                direction = datastore.Query.ASCENDING if order == 1 else datastore.Query.DESCENDING
                order = self.queried_fields[0]
            else:
                direction = datastore.Query.DESCENDING if order.startswith("-") else datastore.Query.ASCENDING
                order = order.lstrip("-")

            if order == self.model._meta.pk.column:
                order = "__key__"
            ordering.append((order, direction))

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

            query = datastore.MultiQuery(queries, ordering)
        else:
            query.Order(*ordering)
        return query

    def _do_fetch(self):
        assert not self.results

        self.results = self._run_query(aggregate_type=self.aggregate_type)
        self.query_done = True

    def _run_query(self, limit=None, start=None, aggregate_type=None):
        query_pre_execute.send(sender=self.model, query=self.gae_query, aggregate=self.aggregate_type)

        if aggregate_type is None:
            if self.included_pks:
                results = iter(datastore.Get(self.included_pks))
                if self.where: #if we have a list of PKs but also with other filters
                    results = iter([x for x in results if self._matches_filters(x, self.where)])
                return results
            else:
                return self.gae_query.Run(limit=limit, start=start)
        elif self.aggregate_type == "count":
            return self.gae_query.Count(limit=limit, start=start)
        else:
            raise RuntimeError("Unsupported query type")

    def _matches_filters(self, result, where_filters):
        if result is None:
            return False
        for column, match_type, match_val in where_filters:
            result_val = result[column]
            result_val = normalise_field_value(result_val)
            match_val = normalise_field_value(match_val)
            try:
                cmp_func = FILTER_CMP_FUNCTION_MAP[match_type]
                if not cmp_func(result_val, match_val):
                    return False
            except KeyError:
                raise NotImplementedError("Filter {0} not (yet?) supported".format(match_type))
        return True

    def next_result(self):
        while True:
            x = self.results.next()

            if self.distinct_on_field: #values for distinct queries
                value = x[self.distinct_on_field]
                value = self.distinct_field_convertor(value)
                if value in self.distinct_values:
                    continue
                else:
                    self.distinct_values.add(value)
                    # Insert modified value into entity before returning the entity. This is dirty,
                    # but Cursor.fetchone (which calls this) wants the entity ID and yet also wants
                    # the correct value for this field. The alternative would be to call
                    # self.distinct_field_convertor again in Cursor.fetchone, but that's wasteful.
                    x[self.distinct_on_field] = value
            return x

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
    def __init__(self, connection, model, objs, fields, raw):
        self.has_pk = any([x.primary_key for x in fields])
        self.entities = []
        self.included_keys = []
        self.model = model

        for obj in objs:
            if self.has_pk:
                self.included_keys.append(Key.from_path(get_datastore_kind(model), obj.pk))

            self.entities.append(
                django_instance_to_entity(connection, model, fields, raw, obj)
            )


    def execute(self):
        if self.has_pk:
            results = []
            #We are inserting, but we specified an ID, we need to check for existence before we Put()
            for key, ent in zip(self.included_keys, self.entities):
                @db.transactional
                def txn():
                    existing = datastore.Query(keys_only=True)
                    existing.Ancestor(key)
                    existing["__key__"] = key
                    res = existing.Count()

                    if res:
                        #FIXME: For now this raises (correctly) when using model inheritance
                        #We need to make model inheritance not insert the base, only the subclass
                        raise IntegrityError("Tried to INSERT with existing key")

                    results.append(datastore.Put(ent))

                txn()

            return results
        else:
            return datastore.Put(self.entities)

class DeleteCommand(object):
    def __init__(self, connection, query):
        self.select = SelectCommand(connection, query, keys_only=True)

    def execute(self):
        self.select.execute()
        datastore.Delete(self.select.results)
        #FIXME: Remove from the cache

class UpdateCommand(object):
    def __init__(self, connection, query):
        self.model = query.model
        self.select = SelectCommand(connection, query, all_fields=True)
        self.values = query.values
        self.connection = connection

    def execute(self):
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
