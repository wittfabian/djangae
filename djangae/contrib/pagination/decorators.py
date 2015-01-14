import random
from functools import partial
from djangae.fields import ComputedCharField

NULL_CHARACTER = u"\0"

def generator(fields, instance):
    """
        Calculates the value needed for a unique ordered representation of the fields
        we are paginating.
    """
    values = []
    for field in fields:
        neg = field.startswith("-")

        value = unicode(instance._meta.get_field(field.lstrip("-")).value_from_object(instance))

        if neg:
            value = u"".join([ unichr(0xffff - ord(x)) for x in value ])
        values.append(value)

    values.append(unicode(instance.pk) or unicode(random.randint(0, 1000000000)))

    return NULL_CHARACTER.join(values)


class PaginatedModel(object):
    """
        A class decorator which automatically generates pre-calculated fields for pagination.

        Specify the orderings (as a list of field tuples) you intend to paginate your models on, and
        additional fields will be added to the model which automatically calculate the appropriate
        value for pagination to work.

        The DatastorePaginator class will implicitly convert your query order_by to use these generated
        fields. Markers will be cached at the end of each page for each query, so that skipping pages
        is fast even when there are many pages.
    """
    def __init__(self, orderings):
        self.orderings = orderings

    def __call__(self, cls):
        """
            Dynamically adds pagination fields to a model depending on
            the orderings you specify
        """
        for ordering in self.orderings:
            names = []
            for field in ordering:
                if field.startswith("-"):
                    names.append("neg_" + field[1:])
                else:
                    names.append(field)

            new_field_name = "pagination_{}".format("_".join(names))
            ComputedCharField(partial(generator, ordering), max_length=500, editable=False).contribute_to_class(cls, new_field_name)

        return cls

paginated_model = PaginatedModel
