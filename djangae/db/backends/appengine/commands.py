#STANDARD LIB
from datetime import datetime
import logging
import copy
from functools import partial
from itertools import chain, product

#LIBRARIES
from django.core.cache import cache
from django.db.backends.mysql.compiler import SQLCompiler
from django.db import IntegrityError
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql.where import AND, OR
from django import dispatch
from google.appengine.api import datastore
from google.appengine.api.datastore import Query
from google.appengine.ext import db

#DJANGAE
from djangae.db.exceptions import CouldBeSupportedError, NotSupportedError
from djangae.db.utils import (
    get_datastore_key,
    django_instance_to_entity,
    get_datastore_kind,
    get_prepared_db_value,
    MockInstance,
    get_top_concrete_parent,
    has_concrete_parents
)
from djangae.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES, add_special_index
from djangae.utils import on_production, in_testing
from djangae.db import constraints, utils

DJANGAE_LOG = logging.getLogger("djangae")

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

REVERSE_OP_MAP = {
    '=':'exact',
    '>':'gt',
    '>=':'gte',
    '<':'lt',
    '<=':'lte',
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


def log_once(logging_call, text, args):
    """
        Only logs one instance of the combination of text and arguments to the passed
        logging function
    """
    identifier = "%s:%s" % (text, args)
    if identifier in log_once.logged:
        return
    logging_call(text % args)
    log_once.logged.add(identifier)

log_once.logged = set()

def explode(target):
    pass


from itertools import product

def normalize_query(query_where, negated=False):
    #1. Explode IN queries into an OR tree e.g. (OR, (x = 1), (x = 2))
    #2. Explode != queries into (AND, (x < y), (x > y))
    #3. Explode startswith into x > y && x < y + u'\ufffd'
    #4. Convert to disjunctive normal form

    output = []
    connector = query_where.connector

    for child in query_where.children:
        if hasattr(child, 'children'): # if child is a whereNode -> recurse! Can a Negated whereNode have children?
            normal = normalize_query(child, negated=query_where.negated)
            for x in normal:
                output.append(x)
        else: # Child is a constraint (literal)
            op = OPERATORS_MAP[child[1]]
            if op:
                if op == '=' and negated:
                    output.append((child[0].col, '>', child[3]))
                    output.append((child[0].col, '<', child[3]))
                else:
                    output.append((child[0].col, op, child[3]))
            else:
                op = child[1]
                if op == 'in':
                    for x in child[3]:
                        output.append([(child[0].col, '=', x)])
    if connector == 'AND':
        # This is where it gets freaky
        ors = [x for x in output if type(x) == list]
        ands = [x for x in output if type(x) == tuple]
        if ors and ands:
            for _or in ors:
                for _and in ands:
                    _or.append(_and)
            output = ors
    if connector == 'OR':
        # My face hurts
        output = [[_or] for _or in output]
    return output


class QueryByKeys(object):
    def __init__(self, query, keys, ordering):
        self.query = query
        self.keys = keys
        self.ordering = ordering

    def Run(self, limit, offset):

        results = sorted((x for x in datastore.Get(self.keys) if x is not None), cmp=partial(utils.django_ordering_comparison, self.ordering))

        if offset:
            results = results[offset:]

        if limit is not None:
            results = results[:limit]

        return ( x for x in results if utils.entity_matches_query(x, self.query) )


class SelectCommand(object):
    def __init__(self, connection, query, keys_only=False, all_fields=False):

        self.original_query = query
        self.connection = connection

        self.limits = (query.low_mark, query.high_mark)

        opts = query.get_meta()
        if not query.default_ordering:
            self.ordering = query.order_by
        else:
            self.ordering = query.order_by or opts.ordering

        if self.ordering:
            ordering = [ x for x in self.ordering if not (isinstance(x, basestring) and "__" in x) ]
            if len(ordering) < len(self.ordering):
                if not on_production() and not in_testing():
                    diff = set(self.ordering) - set(ordering)
                    log_once(DJANGAE_LOG.warning, "The following orderings were ignored as cross-table orderings are not supported on the datastore: %s", diff)
                self.ordering = ordering

        self.distinct = query.distinct
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

        self.exact_pk = None
        self.included_pks = []
        self.excluded_pks = set()

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
                    raise NotSupportedError("Attemping a cross-table select. Maybe? #FIXME")
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
            raise NotSupportedError("Only AND filters are supported for negated queries")

        if where.connector == OR:
            # What we essentially need to do here is this:
            """
            queries = []
            for w in where.children:
                queries.append(self.parse_where_and_check_projection(w, False))
            return MultiQuery(queries)
            """
            # But that would mean combining _build_gae_query and parse_where_and_check_projection
            raise CouldBeSupportedError(
                "Queries with OR could be supported.  See comments above this exception."
            )

        for child in where.children:
            if isinstance(child, tuple):
                constraint, op, annotation, value = child
                packed, value = constraint.process(op, value, self.connection)
                alias, column, db_type = packed

                if op not in ("in", "year") and isinstance(value, list):
                    if len(value[:2]) > 1:
                        raise ValueError("Only IN queries can lookup on a list of values")
                    value = value[0]

                if isinstance(value, (list, tuple)):
                    value = [ self.connection.ops.prep_lookup_value(self.model, x, constraint.field, constraint=constraint) for x in value]
                else:
                    value = self.connection.ops.prep_lookup_value(self.model, value, constraint.field, constraint=constraint)

                #Disable projection if it's not supported
                if self.projection and constraint.col in self.projection:
                    if op in ("exact", "in", "isnull"):
                        #If we are projecting, but we are doing an
                        #equality filter on one of the columns, then we
                        #can't project
                        self.projection = None

                if constraint.field.db_type(self.connection) in ("bytes", "text"):
                    raise NotSupportedError("Text and Blob fields are not indexed by the datastore, so you can't filter on them")

                if negated:
                    if op in ("exact", "in") and constraint.col == self.pk_col:
                        if isinstance(value, (list, tuple)):
                            self.excluded_pks.update(set(value))
                        else:
                            self.excluded_pks.add(value)
                    #else: FIXME when excluded_pks is handled, we can put the
                    #next section in an else block
                    if op == "exact":
                        if self.has_inequality_filter:
                            raise NotSupportedError("You can only specify one inequality filter per query")

                        col = constraint.col
                        result.append((col, "gt_and_lt", value))
                        self.has_inequality_filter = True
                    else:
                        raise NotSupportedError("Unsupported negated lookup: " + op)
                else:
                    if constraint.col == self.pk_col:
                        if (value is None and op == "exact") or (op == "isnull" and value):
                            #If we are looking for a primary key that is None, then we always
                            #just return nothing
                            raise EmptyResultSet()

                        elif op == "exact":
                            if self.exact_pk and self.exact_pk != value:
                                raise EmptyResultSet() #We're trying to filter on two different pks?
                            else:
                                self.exact_pk = value
                                self.included_pks = [ self.exact_pk ]
                        elif op == "in":
                            if isinstance(value, (list, tuple)):
                                self.included_pks.extend(list(value))
                            else:
                                raise ValueError("In query requires a list, found {}".format(value.__class__))
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
        #if not self.included_pks:
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
        inheritance_root = get_top_concrete_parent(self.model)
        self.db_table = inheritance_root._meta.db_table

    def _validate_query_is_possible(self, query):
        """ Given the *django* query, check the following:
            - The query only has one inequality filter
            - The query does no joins
            - The query ordering is compatible with the filters
        """
        #Check for joins
        if query.count_active_tables() > 1:
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

    def _build_gae_query(self):
        """ Build and return the Datstore Query object. """
        combined_filters = []

        query_kwargs = {}

        if self.distinct:
            query_kwargs["distinct"] = True

        if self.keys_only:
            query_kwargs["keys_only"] = self.keys_only
        elif self.projection:
            query_kwargs["projection"] = self.projection

        query = Query(
            self.db_table,
            **query_kwargs
        )

        if has_concrete_parents(self.model) and not self.model._meta.proxy:
            query["class ="] = self.model._meta.db_table

        DJANGAE_LOG.debug("Select query: {0}, {1}".format(self.model.__name__, self.where))
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

            if order == self.model._meta.pk.column or order == "pk":
                order = "__key__"
            ordering.append((order, direction))

        if combined_filters:
            queries = [ query ]
            for column, op, value in combined_filters:
                new_queries = []
                for query in queries:
                    if op == "in":
                        for val in value:
                            new_query = datastore.Query(self.db_table)
                            new_query.update(query)
                            new_query["%s =" % column] = val
                            new_queries.append(new_query)
                    elif op == "gt_and_lt":
                        for tmp_op in ("<", ">"):
                            new_query = datastore.Query(self.db_table)
                            new_query.update(query)
                            new_query["%s %s" % (column, tmp_op)] = value
                            new_queries.append(new_query)
                queries = new_queries

            query = datastore.MultiQuery(queries, ordering)

        elif self.included_pks:
            query = QueryByKeys(query, self.included_pks, ordering)

        elif ordering:
            query.Order(*ordering)
        return query

    def _do_fetch(self):
        assert not self.results

        self.results = self._run_query(
            aggregate_type=self.aggregate_type,
            start=self.limits[0],
            limit=None if self.limits[1] is None else (self.limits[1] - (self.limits[0] or 0))
        )

        self.query_done = True

    def _run_query(self, limit=None, start=None, aggregate_type=None):
        query_pre_execute.send(sender=self.model, query=self.gae_query, aggregate=self.aggregate_type)

        if aggregate_type is None:
            results = self.gae_query.Run(limit=limit, offset=start)
        elif self.aggregate_type == "count":
            return self.gae_query.Count(limit=limit, offset=start)
        else:
            raise RuntimeError("Unsupported query type")

        if self.extra_select:
            # Construct the extra_select into the results set, this is then sorted with fetchone()
            for attr, query in self.extra_select.iteritems():
                tokens = query[0].split()
                length = len(tokens)
                if length == 3:
                    op = REVERSE_OP_MAP.get(tokens[1])
                    if not op:
                        raise RuntimeError("Unsupported extra_select operation {0}".format(tokens[1]))
                    fun = FILTER_CMP_FUNCTION_MAP[op]

                    def lazy_eval(results, attr, fun, token_a, token_b):
                        """ Wraps a list or a generator, applys comparision function
                        token_a is an attribute on the result, the lhs. token_b is the rhs
                        attr is the target attribute to store the result
                        """
                        for result in results:
                            if result is None:
                                yield result

                            lhs = result.get(token_a)
                            lhs_type = type(lhs)
                            rhs = lhs_type(token_b)
                            if isinstance(rhs, basestring):
                                rhs = rhs.strip("'").strip('"') # Strip quotes
                            result[attr] = fun(lhs, rhs)
                            yield result

                    results = lazy_eval(results, attr, fun, tokens[0], tokens[2])

                elif length == 1:

                    def lazy_assign(results, attr, value):
                        """ Wraps a list or a generator, applys attribute assignment
                        """
                        for result in results:
                            if result is None:
                                yield result
                            if isinstance(value, basestring):
                                value = value.strip("'").strip('"')
                                # Horrible SQL type to python conversion attempt
                                try:
                                    value = int(value)
                                except ValueError:
                                    pass
                                # Up for debate
                                # if value == "TRUE":
                                #     value = True
                                # elif value == "FALSE":
                                #     value = False
                            result[attr] = value
                            yield result

                    results = lazy_assign(results, attr, tokens[0])
                else:
                    raise RuntimeError("Unsupported extra_select")
        return results

    def next_result(self):
        while True:
            x = self.results.next()

            if isinstance(x, datastore.Key):
                if x in self.excluded_pks:
                    continue
            elif x.key() in self.excluded_pks:
                continue

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
                #FIXME: Apparently if the PK is required, and obj.pk is None here, we need to raise an IntegrityError
                self.included_keys.append(get_datastore_key(model, obj.pk) if obj.pk else None)
            else:
                #We zip() self.entities and self.included_keys in execute(), so they should be the same legnth
                self.included_keys.append(None)

            self.entities.append(
                django_instance_to_entity(connection, model, fields, raw, obj)
            )

    def execute(self):
        if self.has_pk and not has_concrete_parents(self.model):
            results = []
            #We are inserting, but we specified an ID, we need to check for existence before we Put()
            #We do it in a loop so each check/put is transactional - because it's an ancestor query it shouldn't
            #cost any entity groups

            for key, ent in zip(self.included_keys, self.entities):
                @db.transactional
                def txn():
                    if key is not None:
                        if utils.key_exists(key):
                            raise IntegrityError("Tried to INSERT with existing key")

                    markers = constraints.acquire(self.model, ent)
                    try:
                        results.append(datastore.Put(ent))
                    except:
                        #Make sure we delete any created markers before we re-raise
                        constraints.release_markers(markers)
                        raise

                    entity_post_insert.send(sender=self.model, entity=ent)

                txn()

            return results
        else:
            markers = constraints.acquire_bulk(self.model, self.entities)
            try:
                results = datastore.Put(self.entities)
            except:
                to_delete = chain(*markers)
                constraints.release_markers(to_delete)
                raise

            for ent, m in zip(self.entities, markers):
                constraints.update_instance_on_markers(ent, m)
                entity_post_insert.send(sender=self.model, entity=ent)

            return results

class DeleteCommand(object):
    def __init__(self, connection, query):
        self.select = SelectCommand(connection, query)

    def execute(self):
        self.select.execute()

        #This is a little bit more inefficient than just doing a keys_only query and
        #sending it to delete, but I think this is the sacrifice to make for the unique caching layer
        keys = []
        for entity in self.select.results:
            keys.append(entity.key())
            constraints.release(self.select.model, entity)
            entity_deleted.send(sender=self.select.model, entity=entity)
        datastore.Delete(keys)

class UpdateCommand(object):
    def __init__(self, connection, query):
        self.model = query.model
        self.select = SelectCommand(connection, query, keys_only=True)
        self.values = query.values
        self.connection = connection

    @db.transactional
    def _update_entity(self, key):
        result = datastore.Get(key)
        original = copy.deepcopy(result)

        for field, param, value in self.values:
            result[field.column] = get_prepared_db_value(self.connection, MockInstance(field, value), field)

            #Add special indexed fields
            for index in special_indexes_for_column(self.model, field.column):
                indexer = REQUIRES_SPECIAL_INDEXES[index]
                result[indexer.indexed_column_name(field.column)] = indexer.prep_value_for_database(value)

        entity_pre_update.send(sender=self.model, entity=result)

        to_acquire, to_release = constraints.get_markers_for_update(self.model, original, result)

        #Acquire first, because if that fails then we don't want to alter what's already there
        constraints.acquire_identifiers(to_acquire, result.key())
        try:
            datastore.Put(result)
        except:
            constraints.release_identifiers(to_acquire)
            raise
        else:
            #Now we release the ones we don't want anymore
            constraints.release_identifiers(to_release)

        entity_post_update.send(sender=self.model, entity=result)

    def execute(self):
        self.select.execute()

        results = self.select.results

        i = 0
        for key in results:
            self._update_entity(key)
            i += 1

        return i
