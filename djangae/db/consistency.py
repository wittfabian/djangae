from django.db.models.query import QuerySet


def ensure_instance_included(queryset, created_pk):
    """
        HRD fighting generate for iterating querysets.
        In the common case of having just created an item, this
        inserts the item at the correct place in a subsequent query.

        Currently this ALWAYS inserts the specified item, whether it matches
        the queryset filters or not! It just guarantees that it will be inserted
        in the right place as per the queryset ordering. Only takes into account
        the query.order_by. Patches welcome!
    """

    class EnsuredQuerySet(queryset.__class__):
        def _fetch_all(self):
            super(EnsuredQuerySet, self)._fetch_all()

            try:
                created = self._clone(klass=queryset.__class__).get(pk=created_pk)
            except self.model.DoesNotExist:
                created = None

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
            created_added = False
            for item in self._result_cache:
                # It was returned in the queryset but `created` will
                # be consistent, so replace `item`
                if created and item.pk == created.pk:
                    if created_added:
                        continue
                    else:
                        item = created

                if created and is_less(created, item) and not created_added:
                    created_added = True
                    new_result_cache.append(created)

                new_result_cache.append(item)

            self._result_cache = new_result_cache[:count]

    if isinstance(queryset, QuerySet):
        return queryset._clone(klass=EnsuredQuerySet)
    else:
        return queryset
