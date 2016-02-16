from django.db.models.query import QuerySet


def ensure_instance_included(queryset, included_id):
    """
        HRD fighting generate for iterating querysets.
        In the common case of having just created an item, this
        inserts the item at the correct place in a subsequent query.

        This guarantees that the object will be inserted
        in the right place as per the queryset ordering. Only takes into account
        the query.order_by and not default ordering. Patches welcome!

        If the instance specified by the included_id was deleted, and it comes back
        in the subsequent query, it is removed from the resultset. This might cause an
        off-by-one number of results if you are slicing the queryset.
    """

    class EnsuredQuerySet(queryset.__class__):
        def _fetch_all(self):
            super(EnsuredQuerySet, self)._fetch_all()

            try:
                new_qs = self._clone(klass=queryset.__class__)
                new_qs.query.high_mark = None
                new_qs.query.low_mark = 0
                included = new_qs.get(pk=included_id)
            except self.model.DoesNotExist:
                included = None

            def is_less(lhs, rhs):
                for field in queryset.query.order_by:
                    # Go through the fields specified in the order by
                    negative = field.startswith("-")
                    if negative:
                        field = field[1:]
                        # If the ordering was negated, but the lhs < rhs then return false
                        if getattr(lhs, field, None) < getattr(rhs, field, None):
                            return False
                    else:
                        # If the ordering was not negated, and the lhs >= rhs, return false
                        if getattr(lhs, field, None) >= getattr(rhs, field, None):
                            return False
                else:
                    return True

            new_result_cache = []
            count = self.query.high_mark
            included_added = False
            for item in self._result_cache:
                # It was returned in the queryset but `created` will
                # be consistent, so replace `item`
                if included and item.pk == included.pk:
                    if included_added:
                        continue

                if not included and item.pk == included_id:
                    # The specified object was deleted but came back, so just ignore it
                    continue

                if included and is_less(included, item) and not included_added:
                    included_added = True
                    new_result_cache.append(included)

                if item != included:
                    new_result_cache.append(item)

            self._result_cache = new_result_cache[:count]

    if isinstance(queryset, QuerySet):
        return queryset._clone(klass=EnsuredQuerySet)
    else:
        return queryset
