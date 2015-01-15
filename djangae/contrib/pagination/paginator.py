from django.core.paginator import Paginator
from djangae.contrib.pagination.decorators import _field_name_for_ordering

class PaginationOrderingRequired(RuntimeError):
    pass


def _store_marker(model, query_id, page_number, marker_value):
    """
        For a model and query id, stores the marker value for previously
        queried page number
    """

    pass

def _get_marker(model, query_id, page_number):
    """
        For a model and query_id, returns the marker at the end of the
        previous page. Returns a tuple of (marker, pages) where pages is
        the number of pages we had to go back to find the marker (this is the
        number of pages we need to skip in the result set)
    """
    pass


class DatastorePaginator(Paginator):

    def __init__(self, object_list, per_page, **kwargs):
        if not object_list.ordered:
            object_list.order_by("pk") # Just order by PK by default

        self.original_orderings = object_list.query.order_by
        self.field_required = _field_name_for_ordering(self.original_orderings)

        if not object_list.model._meta.get_field(self.field_required):
            raise PaginationOrderingRequired("No pagination ordering specified for {}".format(self.original_orderings))

        # Wipe out the existing ordering
        object_list = object_list.order_by()

        # Add our replacement ordering
        if len(self.original_orderings) == 1 and self.original_orderings[0].startswith("-"):
            object_list = object_list.order_by("-" + self.field_required)
        else:
            object_list = object_list.order_by(self.field_required)

        super(DatastorePaginator, self).__init__(object_list, per_page, **kwargs)


    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        try:
            marker_value, pages = _get_marker(
                self.object_list.model,
                str(self.object_list.query), #FIXME, make sure this doesn't change for high/low
                number
            )

            if marker_value:
                if len(self.original_orderings) == 1 and self.original_orderings[0].startswith("-"):
                    qs = self.object_list.all().filter(**{"{}__lte".format(self.field_required): marker_value})
                else:
                    qs = self.object_list.all().filter(**{"{}__gt".format(self.field_required): marker_value})
                bottom = pages * self.per_page
                top = bottom + self.per_page
            else:
                qs = self.object_list

            page = self._get_page(qs[bottom:top], number, self)
            return page
        finally:
            _store_marker(
                self.object_list.model,
                str(self.object_list.query),
                number,
                getattr(page.object_list[self.per_page-1], self.field_required)
            )
