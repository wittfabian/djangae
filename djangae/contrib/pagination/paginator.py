from hashlib import md5
from django.db import models
from django.core import paginator
from djangae.contrib.pagination.decorators import _field_name_for_ordering
from django.core.cache import cache

class PaginationOrderingRequired(RuntimeError):
    pass


def _marker_cache_key(model, query_id, page_number):
    cache_key = "_PAGE_MARKER_{}:{}:{}".format(model._meta.db_table, query_id, page_number)
    return cache_key


def _count_cache_key(query_id, per_page):
    cache_key = "_PAGE_COUNTER_{}:{}".format(query_id, per_page)
    return cache_key


def _update_known_count(query_id, per_page, count):
    cache_key = _count_cache_key(query_id, per_page)

    ret = cache.get(cache_key)
    if ret and ret > count:
        return

    cache.set(cache_key, count)


def _get_known_count(query_id, per_page):
    cache_key = _count_cache_key(query_id, per_page)
    ret = cache.get(cache_key)
    if ret:
        return ret
    return 0

def _store_marker(model, query_id, page_number, marker_value):
    """
        For a model and query id, stores the marker value for previously
        queried page number
    """

    cache_key = _marker_cache_key(model, query_id, page_number)
    cache.set(cache_key, marker_value, 30*60)


def _get_marker(model, query_id, page_number):
    """
        For a model and query_id, returns the marker at the end of the
        previous page. Returns a tuple of (marker, pages) where pages is
        the number of pages we had to go back to find the marker (this is the
        number of pages we need to skip in the result set)
    """

    counter = page_number - 1
    pages_skipped = 0

    while counter:
        cache_key = _marker_cache_key(model, query_id, counter)
        ret = cache.get(cache_key)

        if ret:
            return ret, pages_skipped

        counter -= 1
        pages_skipped += 1

    # If we get here then we couldn't find a stored marker anywhere
    return None, pages_skipped


def queryset_identifier(queryset):
    """ Returns a string that uniquely identifies this query excluding its low and high mark"""

    hasher = md5()
    hasher.update(str(queryset.query.where))
    hasher.update(str(queryset.query.order_by))
    return hasher.hexdigest()


class DatastorePaginator(paginator.Paginator):
    """
        A paginator that works with the @paginated_model class decorator to efficiently
        return paginated sets on the appengine datastore
    """

    def __init__(self, object_list, per_page, readahead=10, **kwargs):
        if not object_list.ordered:
            object_list.order_by("pk") # Just order by PK by default

        self.original_orderings = object_list.query.order_by
        self.field_required = _field_name_for_ordering(self.original_orderings[:])
        self.readahead = readahead

        try:
            object_list.model._meta.get_field(self.field_required)
        except models.FieldDoesNotExist:
            raise PaginationOrderingRequired("No pagination ordering specified for {}".format(self.original_orderings))

        # Wipe out the existing ordering
        object_list = object_list.order_by()

        # Add our replacement ordering
        if len(self.original_orderings) == 1 and self.original_orderings[0].startswith("-"):
            object_list = object_list.order_by("-" + self.field_required)
        else:
            object_list = object_list.order_by(self.field_required)

        # If we specified an initial count up to, then count some things
        queryset_id = queryset_identifier(object_list)
        upper_count_limit = readahead * per_page
        if _get_known_count(queryset_id, per_page) < upper_count_limit:
            object_count = object_list[:upper_count_limit].count()
            _update_known_count(queryset_id, per_page, object_count)

        super(DatastorePaginator, self).__init__(object_list, per_page, **kwargs)

    @property
    def count(self):
        return _get_known_count(queryset_identifier(self.object_list), self.per_page)

    def validate_number(self, number):
        """
        Validates the given 1-based page number.
        """
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise paginator.PageNotAnInteger('That page number is not an integer')
        if number < 1:
            raise paginator.EmptyPage('That page number is less than 1')

        return number

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        queryset_id = queryset_identifier(self.object_list)

        marker_value, pages = _get_marker(
            self.object_list.model,
            queryset_id,
            number
        )

        if marker_value:
            if len(self.original_orderings) == 1 and self.original_orderings[0].startswith("-"):
                qs = self.object_list.all().filter(**{"{}__lt".format(self.field_required): marker_value})
            else:
                qs = self.object_list.all().filter(**{"{}__gt".format(self.field_required): marker_value})
            bottom = pages * self.per_page # We have to skip the pages here
            top = bottom + self.per_page
        else:
            qs = self.object_list

        results = list(qs[bottom:top + (self.per_page * self.readahead)])

        if not results:
            raise paginator.EmptyPage("That page contains no results")

        known_count = ((number - 1) * self.per_page) + len(results)
        _update_known_count(queryset_id, self.per_page, known_count)

        page = self._get_page(results[:top], number, self)

        _store_marker(
            self.object_list.model,
            queryset_id,
            number,
            getattr(page.object_list[self.per_page-1], self.field_required)
        )

        return page
