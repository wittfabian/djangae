from django.db.models import Q

from .models import (
    WORD_DOCUMENT_JOIN_STRING,
    DocumentData,
    WordIndex,
)


def _tokenize_query_string(query_string):
    """
        Returns a list of WordDocumentField keys to fetch
        based on the query_string
    """

    # We always lower case. Even Atom fields are case-insensitive
    query_string = query_string.lower()

    branches = query_string.split(" or ")

    # Split into [(fieldname, query)] tuples for each branch
    field_queries = [
        tuple(x.split(":", 1)) if ":" in x else (None, x)
        for x in branches
    ]

    # Remove empty queries
    field_queries = [x for x in field_queries if x[1].strip()]

    # By this point, given the following query:
    # pikachu OR name:charmander OR name:"Mew Two" OR "Mr Mime"
    # we should have:
    # [(None, "pikachu"), ("name", "charmander"), ("name", '"mew two"'), (None, '"mr mime"')]
    # Note that exact matches will have quotes around them

    result = [
        ("exact" if x[1][0] == '"' and x[1][-1] == '"' else "word", x[0], x[1].strip('"'))
        for x in field_queries
    ]

    # Now we should have
    # [
    #     ("word", None, "pikachu"), ("word", "name", "charmander"),
    #     ("exact", "name", 'mew two'), ("exact", None, 'mr mime')
    # ]

    return result


def build_document_queryset(query_string, index):
    assert(index.id)

    tokenization = _tokenize_query_string(query_string)
    if not tokenization:
        return DocumentData.objects.none()

    filters = Q()

    # All queries need to prefix the index
    prefix = "%s%s" % (str(index.id), WORD_DOCUMENT_JOIN_STRING)

    for kind, field, string in tokenization:
        if kind == "word":
            if not field:
                start = "%s%s%s" % (prefix, string, WORD_DOCUMENT_JOIN_STRING)
                end = "%s%s%s%s" % (prefix, string, chr(0x10FFFF), WORD_DOCUMENT_JOIN_STRING)
                filters |= Q(pk__gte=start, pk__lt=end)
            else:
                start = "%s%s%s%s%s" % (prefix, string, WORD_DOCUMENT_JOIN_STRING, field, WORD_DOCUMENT_JOIN_STRING)
                end = "%s%s%s%s%s" % (
                    prefix, string + chr(0x10FFFF), WORD_DOCUMENT_JOIN_STRING, field, WORD_DOCUMENT_JOIN_STRING
                )
                filters |= Q(pk__gte=start, pk__lt=end)
        else:
            raise NotImplementedError("Need to implement exact matching")

    document_ids = [
        WordIndex.document_id_from_pk(x)
        for x in WordIndex.objects.filter(filters).values_list("pk", flat=True)
    ]

    return DocumentData.objects.filter(pk__in=document_ids)
