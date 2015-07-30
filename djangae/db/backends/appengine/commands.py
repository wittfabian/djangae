#STANDARD LIB
from datetime import datetime
import logging
import copy
import re
from functools import partial
from itertools import chain, groupby

#LIBRARIES
import django
from django.db import DatabaseError
from django.core.exceptions import FieldError
from django.db.models.fields import FieldDoesNotExist

from django.core.cache import cache
from django.db import IntegrityError
from django.db.models.sql.datastructures import EmptyResultSet
from django.db.models.sql import query
from django.db.models.sql.where import EmptyWhere
from django.db.models.fields import AutoField

from google.appengine.api import datastore, datastore_errors
from google.appengine.api.datastore import Query
from google.appengine.ext import db

#DJANGAE
from djangae.db.backends.appengine.dbapi import CouldBeSupportedError, NotSupportedError
from djangae.db.utils import (
    get_datastore_key,
    django_instance_to_entity,
    get_prepared_db_value,
    MockInstance,
    get_top_concrete_parent,
    get_concrete_parents,
    has_concrete_parents,
    get_field_from_column
)
from djangae.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES, add_special_index
from djangae.utils import on_production, memoized
from djangae.db import constraints, utils
from djangae.db.backends.appengine import caching
from djangae.db.unique_utils import query_is_unique
from djangae.db.backends.appengine import transforms
from djangae.db.caching import clear_context_cache

DATE_TRANSFORMS = {
    "year": transforms.year_transform,
    "month": transforms.month_transform,
    "day": transforms.day_transform,
    "hour": transforms.hour_transform,
    "minute": transforms.minute_transform,
    "second": transforms.second_transform
}

DJANGAE_LOG = logging.getLogger("djangae")

OPERATORS_MAP = {
    'exact': '=',
    'gt': '>',
    'gte': '>=',
    'lt': '<',
    'lte': '<=',

    # The following operators are supported with special code below.
    'isnull': None,
    'in': None,
    'range': None,
}

EXTRA_SELECT_FUNCTIONS = {
    '+': lambda x, y: x + y,
    '-': lambda x, y: x - y,
    '/': lambda x, y: x / y,
    '*': lambda x, y: x * y,
    '<': lambda x, y: x < y,
    '>': lambda x, y: x > y,
    '=': lambda x, y: x == y
}

REVERSE_OP_MAP = {
    '=':'exact',
    '>':'gt',
    '>=':'gte',
    '<':'lt',
    '<=':'lte',
}

INEQUALITY_OPERATORS = frozenset(['>', '<', '<=', '>='])


def _cols_from_where_node(where_node):
    cols = where_node.get_cols() if hasattr(where_node, 'get_cols') else where_node.get_group_by_cols()
    return cols

def _get_tables_from_where(where_node):
    cols = _cols_from_where_node(where_node)
    if django.VERSION[1] < 8:
        return list(set([x[0] for x in cols if x[0] ]))
    else:
        return list(set([x.alias for x in cols]))


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
    """
        Painfully, sometimes the Datastore returns dates as datetime objects, and sometimes
        it returns them as unix timestamps in microseconds!!
    """
    if isinstance(value, long):
        return datetime.fromtimestamp(value / 1000000)
    return value

def coerce_unicode(value):
    if isinstance(value, str):
        try:
            value = value.decode('utf-8')
        except UnicodeDecodeError:
            # This must be a Django databaseerror, because the exception happens too
            # early before Django's exception wrapping can take effect (e.g. it happens on SQL
            # construction, not on execution.
            raise DatabaseError("Bytestring is not encoded in utf-8")

    # The SDK raises BadValueError for unicode sub-classes like SafeText.
    return unicode(value)


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


def parse_constraint(child, connection, negated=False):
    if isinstance(child, tuple):
        # First, unpack the constraint
        constraint, op, annotation, value = child
        was_list = isinstance(value, (list, tuple))
        if isinstance(value, query.Query):
            value = value.get_compiler(connection.alias).as_sql()[0].execute()
        else:
            packed, value = constraint.process(op, value, connection)
        alias, column, db_type = packed
        field = constraint.field
    else:
        # Django 1.7+
        field = child.lhs.target
        column = child.lhs.target.column
        op = child.lookup_name
        value = child.rhs
        annotation = value
        was_list = isinstance(value, (list, tuple))

        if isinstance(value, query.Query):
            value = value.get_compiler(connection.alias).as_sql()[0].execute()
        elif value != []:
            value = child.lhs.output_field.get_db_prep_lookup(
                child.lookup_name, child.rhs, connection, prepared=True)


    is_pk = field and field.primary_key

    if column == "id" and op == "iexact" and is_pk and isinstance(field, AutoField):
        # When new instance is created, automatic primary key 'id' does not generate '_idx_iexact_id'.
        # As the primary key 'id' (AutoField) is integer and is always case insensitive, we can deal with 'id_iexact=' query by using 'exact' rather than 'iexact'.
        op = "exact"

    if field and field.db_type(connection) in ("bytes", "text"):
        raise NotSupportedError("Text and Blob fields are not indexed by the datastore, so you can't filter on them")

    if op not in REQUIRES_SPECIAL_INDEXES:
        # Don't convert if this op requires special indexes, it will be handled there
        if field:
            value = [ connection.ops.prep_lookup_value(field.model, x, field, column=column) for x in value]

        # Don't ask me why, but on Django 1.6 constraint.process on isnull wipes out the value (it returns an empty list)
        # so we have to special case this to use the annotation value instead
        if op == "isnull":
            if annotation is not None:
                value = [ annotation ]

            if is_pk and value[0]:
                raise EmptyResultSet()

        if not was_list:
            value = value[0]
    else:
        if negated:
            raise CouldBeSupportedError("Special indexing does not currently supported negated queries. See #80")

        if not was_list:
            value = value[0]

        add_special_index(field.model, column, op)  # Add the index if we can (e.g. on dev_appserver)

        if op not in special_indexes_for_column(field.model, column):
            raise RuntimeError("There is a missing index in your djangaeidx.yaml - \n\n{0}:\n\t{1}: [{2}]".format(
                field.model, column, op)
            )

        indexer = REQUIRES_SPECIAL_INDEXES[op]
        value = indexer.prep_value_for_query(value)
        column = indexer.indexed_column_name(column, value=value)
        op = indexer.prep_query_operator(op)

    return column, op, value


def convert_keys_to_entities(results):
    """
        If for performance reasons we do a keys_only query, then the result
        of the query will be a list of keys, not a list of entities. Here
        we convert to a FakeEntity type which should be enough for the rest of the
        pipeline to process without knowing any different!
    """

    class FakeEntity(dict):
        def __init__(self, key):
            self._key = key

        def key(self):
            return self._key

    for result in results:
        if isinstance(result, datastore.Key):
            yield FakeEntity(result)
        else:
            yield FakeEntity(result.key())


def _convert_entity_based_on_query_options(entity, opts):
    if opts.keys_only:
        return entity.key()

    if opts.projection:
        for k in entity.keys()[:]:
            if k not in list(opts.projection) + ["class"]:
                del entity[k]

    return entity


def _get_key(query):
    return query["__key__ ="]

class QueryByKeys(object):
    def __init__(self, model, queries, ordering):
        self.model = model
        self.queries = queries
        self.queries_by_key = { a: list(b) for a, b in groupby(queries, lambda x: _get_key(x)) }
        self.ordering = ordering
        self._Query__kind = queries[0]._Query__kind

    def Run(self, limit=None, offset=None):
        assert not self.queries[0]._Query__ancestor_pb #FIXME: We don't handle this yet

        # FIXME: What if the query options differ?
        opts = self.queries[0]._Query__query_options

        results = None

        # If we have a single key lookup going on, just hit the cache
        if len(self.queries_by_key) == 1:
            keys = self.queries_by_key.keys()
            ret = caching.get_from_cache_by_key(keys[0])
            if ret is not None:
                results = [ret]

        # If there was nothing in the cache, or we had more than one key, then use Get()
        if results is None:
            keys = self.queries_by_key.keys()
            results = datastore.Get(keys)
            for result in results:
                if result is None:
                    continue
                caching.add_entity_to_cache(self.model, result, caching.CachingSituation.DATASTORE_GET)
            results = sorted((x for x in results if x is not None), cmp=partial(utils.django_ordering_comparison, self.ordering))

        results = [
            _convert_entity_based_on_query_options(x, opts)
            for x in results if any([ utils.entity_matches_query(x, qry) for qry in self.queries_by_key[x.key()]])
        ]

        if offset:
            results = results[offset:]

        if limit is not None:
            results = results[:limit]

        return iter(results)

    def Count(self, limit, offset):
        return len([ x for x in self.Run(limit, offset) ])


class NoOpQuery(object):
    def Run(self, limit, offset):
        return []

    def Count(self, limit, offset):
        return 0


class UniqueQuery(object):
    """
        This mimics a normal query but hits the cache if possible. It must
        be passed the set of unique fields that form a unique constraint
    """
    def __init__(self, unique_identifier, gae_query, model):
        self._identifier = unique_identifier
        self._gae_query = gae_query
        self._model = model

    def Run(self, limit, offset):
        opts = self._gae_query._Query__query_options
        if opts.keys_only or opts.projection:
            return self._gae_query.Run(limit=limit, offset=offset)

        ret = caching.get_from_cache(self._identifier)
        if ret is not None and not utils.entity_matches_query(ret, self._gae_query):
            ret = None

        if ret is None:
            # We do a fast keys_only query to get the result
            keys_query = Query(self._gae_query._Query__kind, keys_only=True)
            keys_query.update(self._gae_query)
            keys = keys_query.Run(limit=limit, offset=offset)

            # Do a consistent get so we don't cache stale data, and recheck the result matches the query
            ret = [ x for x in datastore.Get(keys) if x and utils.entity_matches_query(x, self._gae_query) ]
            if len(ret) == 1:
                caching.add_entity_to_cache(self._model, ret[0], caching.CachingSituation.DATASTORE_GET)
            return iter(ret)

        return iter([ ret ])

    def Count(self, limit, offset):
        return sum(1 for x in self.Run(limit, offset))


def _convert_ordering(query):
    if not query.default_ordering:
        result = query.order_by
    else:
        result = query.order_by or query.get_meta().ordering

    if query.extra_order_by:
        # This is a best attempt at ordering by extra select, it covers the cases
        # in the Django tests, but use this functionality with care
        all_fields = query.get_meta().get_all_field_names()
        new_ordering = []
        for col in query.extra_order_by:
            # If the query in the extra order by is part of the extra select
            # and the extra select is just an alias, then use the original column
            if col in query.extra_select:
                if query.extra_select[col][0] in all_fields:
                    new_ordering.append(query.extra_select[col][0])
                else:
                    # It wasn't an alias, probably can't support it
                    raise NotSupportedError("Unsupported extra_order_by: {}".format(query.extra_order_by))
            else:
                # Not in the extra select, probably just a column so use it if it is
                if col in all_fields:
                    new_ordering.append(col)
                else:
                    raise NotSupportedError("Unsupported extra_order_by: {}".format(query.extra_order_by))

        result = tuple(new_ordering)

    if result:
        # We factor out cross-table orderings (rather than raising NotSupportedError) otherwise we'll break
        # the admin which uses them. We log a warning when this happens though
        try:
            ordering = []
            for name in result:
                if name == "?":
                    raise NotSupportedError("Random ordering is not supported on the datastore")

                if not (isinstance(name, basestring) and "__" in name):
                    if isinstance(name, basestring):
                        if name.lstrip("-") == "pk":
                            field_column = query.model._meta.pk.column
                        else:
                            field = query.model._meta.get_field_by_name(name.lstrip("-"))[0]
                            field_column = field.column
                        ordering.append(field_column if not name.startswith("-") else "-{}".format(field_column))
                    else:
                        ordering.append(name)

        except FieldDoesNotExist:
            opts = query.model._meta
            available = opts.get_all_field_names()
            raise FieldError("Cannot resolve keyword %r into field. "
                "Choices are: %s" % (name, ", ".join(available))
            )

        if len(ordering) < len(result):
            diff = set(result) - set(ordering)
            log_once(
                DJANGAE_LOG.warning if not on_production() else DJANGAE_LOG.debug,
                "The following orderings were ignored as cross-table orderings are not supported on the datastore: %s", diff
            )
        result = ordering


    return result

def _apply_extra_to_entity(extra_select, entity, pk_col):
    """
        Obviously the datastore doesn't support extra columns, but we can emulate simple
        extra selects as we iterate the results. This function does that!
    """

    def prep_value(attr):
        if attr == pk_col:
            attr = entity.key().id_or_name()
        else:
            attr = entity[attr] if attr in entity else attr

        try:
            attr = int(attr)
        except (TypeError, ValueError):
            pass

        if isinstance(attr, basestring):
            if (attr[0], attr[-1]) == ("'", "'"):
                attr = attr[1:-1]
            elif (attr[0], attr[-1]) == ('"', '"'):
                attr = attr[1:-1]
        return attr

    for column, (select, _) in extra_select.iteritems():

        arithmetic_regex = "(\w+)\s?([+|-|/|*|\=])\s?([\w|'|\"]+)"
        match = re.match(arithmetic_regex, select)
        if match:
            lhs = match.group(1)
            op = match.group(2)
            rhs = match.group(3)

            lhs = prep_value(lhs)
            rhs = prep_value(rhs)

            fun = EXTRA_SELECT_FUNCTIONS.get(op)
            if not fun:
                raise NotSupportedError("Unimplemented extra select operation: '%s'" % op)

            entity[column] = fun(lhs, rhs)
        else:
            rhs = prep_value(select)
            entity[column] = rhs

    return entity

from djangae.db.backends.appengine.query import transform_query
from djangae.db.backends.appengine.dnf import normalize_query

def convert_django_ordering_to_gae(ordering):
    result = []

    for column in ordering:
        if column.startswith("-"):
            result.append((column.lstrip("-"), datastore.Query.DESCENDING))
        else:
            result.append((column, datastore.Query.ASCENDING))
    return result

def wrap_result_with_functor(results, func):
    for result in results:
        result = func(result)
        if result is not None:
            yield result


def can_perform_datastore_get(normalized_query):
    """
        Given a normalized query, returns True if there is an equality
        filter on a key in each branch of the where
    """
    assert normalized_query.is_normalized

    for and_branch in normalized_query.where.children:
        if and_branch.is_leaf:
            if (and_branch.column != "__key__" or and_branch.operator != "="):
                return False
        else:
            key_found = False
            for filter_node in and_branch.children:
                assert filter_node.is_leaf

                if filter_node.column == "__key__":
                    if filter_node.operator == "=":
                        key_found = True
                        break

            if not key_found:
                return False

    return True


class NewSelectCommand(object):
    def __init__(self, connection, query, keys_only=False):
        self.query = normalize_query(transform_query(connection, query))
        self.original_query = query
        self.keys_only = keys_only or [x.field for x in query.select] == [ query.model._meta.pk ]

        self.excluded_pks = []
        self.included_pks = []

    def _sanity_check(self):
        if self.query.distinct and not self.query.columns:
            raise NotSupportedError("Tried to perform distinct query when projection wasn't possible")

    def _build_query(self):
        self._sanity_check()

        queries = []

        query_kwargs = {
            "kind": str(self.query.tables[0]),
            "distinct": self.query.distinct or None,
            "keys_only": self.keys_only or None,
            "projection": self.query.columns or None
        }

        ordering = convert_django_ordering_to_gae(self.query.order_by)

        if self.query.distinct and not ordering:
            # If we specified we wanted a distinct query, but we didn't specify
            # an ordering, we must set the ordering to the distinct columns, otherwise
            # App Engine shouts at us. Nastily. And without remorse.
            ordering = self.query.columns

        # Deal with the no filters case
        if self.query.where is None:
            query = Query(
                **query_kwargs
            )
            query.Order(*ordering)
            return query

        assert self.query.where

        # Go through the normalized query tree
        for and_branch in self.query.where.children:
            query = Query(
                **query_kwargs
            )

            filters = [ and_branch ] if and_branch.is_leaf else and_branch.children

            for filter_node in filters:
                lookup = "{} {}".format(filter_node.column, filter_node.operator)

                if lookup in query and not isinstance(query[lookup], (list, tuple)):
                    query[lookup] = [ query[lookup ] ] + [ filter_node.value ]
                else:
                    query[lookup] = filter_node.value

            if ordering:
                query.Order(*ordering)
            queries.append(query)

        if can_perform_datastore_get(self.query):
            # Yay for optimizations!
            return QueryByKeys(self.query.model, queries, ordering)

        unique_identifier = query_is_unique(self.query)
        if unique_identifier:
            # Yay for optimizations!
            return UniqueQuery(unique_identifier, self.query, self.query.model)

        if len(queries) == 1:
            return queries[0]
        else:
            return datastore.MultiQuery(queries, ordering)

    def _fetch_results(self, query):
        # If we're manually excluding PKs, and we've specified a limit to the results
        # we need to make sure that we grab more than we were asked for otherwise we could filter
        # out too many! These are again limited back to the original request limit
        # while we're processing the results later

        high_mark = self.query.high_mark
        low_mark = self.query.low_mark

        excluded_pk_count = 0
        if self.excluded_pks and high_mark:
            excluded_pk_count = len(self.excluded_pks)
            high_mark += excluded_pk_count

        limit = None if high_mark is None else (high_mark - (low_mark or 0))
        offset = low_mark or 0

        if self.query.kind == "COUNT":
            self.results = (x for x in [query.Count(limit=limit, offset=offset)])
            return
        elif self.query.kind == "AVERAGE":
            raise ValueError("AVERAGE not yet supported")
        else:
            self.results = query.Run(limit=limit, offset=offset)

        # Ensure that the results returned is reset
        self.results_returned = 0

        def increment_returned_results(result):
            self.results_returned += 1
            return result

        def convert_key_to_entity(result):
            class FakeEntity(dict):
                def __init__(self, key):
                    self._key = key

                def key(self):
                    return self._key

            return FakeEntity(result)

        def rename_pk_field(result):
            if result is None:
                return result

            result[self.query.model._meta.pk.column] = result.key().id_or_name()
            return result

        def process_extra_selects(result):
            """
                We handle extra selects by generating the new columns from
                each result. We can handle simple boolean logic and operators.
            """
            extra_selects = self.query.extra_selects
            model_fields = self.query.model._meta.fields

            DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S")

            def process_arg(arg):
                if arg.startswith("'") and arg.endswith("'"):
                    # String literal
                    arg = arg.strip("'")
                    # Check to see if this is a date
                    for date in DATE_FORMATS:
                        try:
                            value = datetime.strptime(arg, date)
                            return value
                        except ValueError:
                            continue
                    return arg
                elif arg in [ x.column for x in model_fields ]:
                    # Column value
                    return result.get(arg)

                # Handle NULL
                if arg.lower() == 'null':
                    return None
                elif arg.lower() == 'true':
                    return True
                elif arg.lower() == 'false':
                    return False

                # Just a plain old literal
                return arg

            for col, select in extra_selects:
                result[col] = select[0](*[ process_arg(x) for x in select[1] ])

            return result

        self.results = wrap_result_with_functor(self.results, increment_returned_results)

        # If this is a keys only query, we need to generate a fake entity
        # for each key in the result set
        if self.keys_only:
            self.results = wrap_result_with_functor(self.results, convert_key_to_entity)

        self.results = wrap_result_with_functor(self.results, rename_pk_field)
        self.results = wrap_result_with_functor(self.results, process_extra_selects)

    def execute(self):
        self.gae_query = self._build_query()
        self._fetch_results(self.gae_query)


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

        # Delete the markers we need to
        from djangae.db.constraints import UniqueMarker
        query = datastore.Query(UniqueMarker.kind(), keys_only=True)
        query["__key__ >="] = datastore.Key.from_path(UniqueMarker.kind(), self.table)
        query["__key__ <"] = datastore.Key.from_path(UniqueMarker.kind(), u"{}{}".format(self.table, u'\ufffd'))
        while query.Count():
            datastore.Delete(query.Run())

        cache.clear()
        clear_context_cache()

@db.non_transactional
def reserve_id(kind, id_or_name):
    from google.appengine.api.datastore import _GetConnection
    key = datastore.Key.from_path(kind, id_or_name)
    _GetConnection()._async_reserve_keys(None, [key])


class InsertCommand(object):
    def __init__(self, connection, model, objs, fields, raw):
        self.has_pk = any([x.primary_key for x in fields])
        self.entities = []
        self.included_keys = []
        self.model = model

        for obj in objs:
            if self.has_pk:
                # We must convert the PK value here, even though this normally happens in django_instance_to_entity otherwise
                # custom PK fields don't work properly
                value = model._meta.pk.get_db_prep_save(model._meta.pk.pre_save(obj, True), connection)
                self.included_keys.append(get_datastore_key(model, value) if value else None)
                if not self.model._meta.pk.blank and self.included_keys[-1] is None:
                    raise IntegrityError("You must specify a primary key value for {} instances".format(model))
            else:
                # We zip() self.entities and self.included_keys in execute(), so they should be the same length
                self.included_keys.append(None)

            self.entities.append(
                django_instance_to_entity(connection, model, fields, raw, obj)
            )

    def execute(self):
        if self.has_pk and not has_concrete_parents(self.model):
            results = []
            # We are inserting, but we specified an ID, we need to check for existence before we Put()
            # We do it in a loop so each check/put is transactional - because it's an ancestor query it shouldn't
            # cost any entity groups

            was_in_transaction = datastore.IsInTransaction()

            for key, ent in zip(self.included_keys, self.entities):
                @db.transactional
                def txn():
                    if key is not None:
                        if utils.key_exists(key):
                            raise IntegrityError("Tried to INSERT with existing key")

                    id_or_name = key.id_or_name()
                    if isinstance(id_or_name, basestring) and id_or_name.startswith("__"):
                        raise NotSupportedError("Datastore ids cannot start with __. Id was %s" % id_or_name)

                    if not constraints.constraint_checks_enabled(self.model):
                        # Fast path, just insert
                        results.append(datastore.Put(ent))
                    else:
                        markers = constraints.acquire(self.model, ent)
                        try:
                            results.append(datastore.Put(ent))
                            if not was_in_transaction:
                                # We can cache if we weren't in a transaction before this little nested one
                                caching.add_entity_to_cache(self.model, ent, caching.CachingSituation.DATASTORE_GET_PUT)
                        except:
                            # Make sure we delete any created markers before we re-raise
                            constraints.release_markers(markers)
                            raise

                # Make sure we notify app engine that we are using this ID
                # FIXME: Copy ancestor across to the template key
                reserve_id(key.kind(), key.id_or_name())

                txn()

            return results
        else:

            if not constraints.constraint_checks_enabled(self.model):
                # Fast path, just bulk insert
                results = datastore.Put(self.entities)
                for entity in self.entities:
                    caching.add_entity_to_cache(self.model, entity, caching.CachingSituation.DATASTORE_PUT)
                return results
            else:
                markers = []
                try:
                    #FIXME: We should rearrange this so that each entity is handled individually like above. We'll
                    # lose insert performance, but gain consistency on errors which is more important
                    markers = constraints.acquire_bulk(self.model, self.entities)

                    results = datastore.Put(self.entities)
                    for entity in self.entities:
                        caching.add_entity_to_cache(self.model, entity, caching.CachingSituation.DATASTORE_PUT)

                except:
                    to_delete = chain(*markers)
                    constraints.release_markers(to_delete)
                    raise

                for ent, k, m in zip(self.entities, results, markers):
                    ent.__key = k
                    constraints.update_instance_on_markers(ent, m)

                return results

    def lower(self):
        """
            This exists solely for django-debug-toolbar compatibility.
        """
        return str(self).lower()


class DeleteCommand(object):
    def __init__(self, connection, query):
        self.model = query.model
        self.select = NewSelectCommand(connection, query, keys_only=True)

    def execute(self):
        self.select.execute()

        # This is a little bit more inefficient than just doing a keys_only query and
        # sending it to delete, but I think this is the sacrifice to make for the unique caching layer
        keys = []

        def spawn_query(kind, key):
            qry = Query(kind)
            qry["__key__ ="] = key
            return qry

        queries = [spawn_query(x.key().kind(), x.key()) for x in self.select.results]
        if not queries:
            return

        for entity in QueryByKeys(self.model, queries, []).Run():
            keys.append(entity.key())

            # Delete constraints if that's enabled
            if constraints.constraint_checks_enabled(self.model):
                constraints.release(self.model, entity)

            caching.remove_entity_from_cache_by_key(entity.key())
        datastore.Delete(keys)

    def lower(self):
        """
            This exists solely for django-debug-toolbar compatibility.
        """
        return str(self).lower()


class UpdateCommand(object):
    def __init__(self, connection, query):
        self.model = query.model
        self.select = NewSelectCommand(connection, query, keys_only=True)
        self.values = query.values
        self.connection = connection

    def lower(self):
        """
            This exists solely for django-debug-toolbar compatibility.
        """
        return str(self).lower()

    @db.transactional
    def _update_entity(self, key):
        caching.remove_entity_from_cache_by_key(key)

        try:
            result = datastore.Get(key)
        except datastore_errors.EntityNotFoundError:
            # Return false to indicate update failure
            return False

        if (
            isinstance(self.select.gae_query, (Query, UniqueQuery)) # ignore QueryByKeys and NoOpQuery
            and not utils.entity_matches_query(result, self.select.gae_query)
        ):
            # Due to eventual consistency they query may have returned an entity which no longer
            # matches the query
            return False

        original = copy.deepcopy(result)

        instance_kwargs = {field.attname:value for field, param, value in self.values}

        # Note: If you replace MockInstance with self.model, you'll find that some delete
        # tests fail in the test app. This is because any unspecified fields would then call
        # get_default (even though we aren't going to use them) which may run a query which
        # fails inside this transaction. Given as we are just using MockInstance so that we can
        # call django_instance_to_entity it on it with the subset of fields we pass in,
        # what we have is fine.
        instance = MockInstance(**instance_kwargs)

        # Update the entity we read above with the new values
        result.update(django_instance_to_entity(
            self.connection, self.model,
            [ x[0] for x in self.values],  # Pass in the fields that were updated
            True, instance)
        )

        if not constraints.constraint_checks_enabled(self.model):
            # The fast path, no constraint checking
            datastore.Put(result)
            caching.add_entity_to_cache(self.model, result, caching.CachingSituation.DATASTORE_PUT)
        else:
            to_acquire, to_release = constraints.get_markers_for_update(self.model, original, result)

            # Acquire first, because if that fails then we don't want to alter what's already there
            constraints.acquire_identifiers(to_acquire, result.key())
            try:
                datastore.Put(result)
                caching.add_entity_to_cache(self.model, result, caching.CachingSituation.DATASTORE_PUT)
            except:
                constraints.release_identifiers(to_acquire)
                raise
            else:
                # Now we release the ones we don't want anymore
                constraints.release_identifiers(to_release)

        # Return true to indicate update success
        return True

    def execute(self):
        self.select.execute()

        results = self.select.results

        i = 0
        for result in results:
            if self._update_entity(result.key()):
                # Only increment the count if we successfully updated
                i += 1

        return i
