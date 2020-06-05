from django.db.models import Q

from .models import (
    WORD_DOCUMENT_JOIN_STRING,
    DocumentStats,
    WordDocumentField,
)


def _tokenize_query_string(query_string):
    """
        Returns a list of WordDocumentField keys to fetch
        based on the query_string
    """

    # Normalize OR operators
    query_string = query_string.replace(" or ", " OR ")

    branches = query_string.split(" OR ")

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
    # [(None, "pikachu"), ("name", "charmander"), ("name", '"Mew Two"'), (None, '"Mr Mime"')]
    # Note that exact matches will have quotes around them

    result = [
        ("exact" if x[1][0] == '"' and x[1][-1] == '"' else "word", x[0], x[1].strip('"'))
        for x in field_queries
    ]

    # Now we should have
    # [
    #     ("word", None, "pikachu"), ("word", "name", "charmander"),
    #     ("exact", "name", 'Mew Two'), ("exact", None, 'Mr Mime')
    # ]
    return result


def build_document_queryset(query_string):
    tokenization = _tokenize_query_string(query_string)
    if not tokenization:
        return DocumentStats.objects.none()

    filters = []

    for kind, field, string in tokenization:
        if kind == "word":
            if not field:
                start = "%s%s" % (string, WORD_DOCUMENT_JOIN_STRING)
                end = "%s%s" % (string + chr(0x10FFFF), WORD_DOCUMENT_JOIN_STRING)
                filters.append(Q(pk__gte=start, pk__lt=end))
            else:
                start = "%s%s%s" % (string, WORD_DOCUMENT_JOIN_STRING, field)
                end = "%s%s%s" % (string + chr(0x10FFFF), WORD_DOCUMENT_JOIN_STRING, field)
                filters.append(Q(pk__gte=start, pk__lt=end))
        else:
            raise NotImplementedError("Need to implement exact matching")

    document_ids = WordDocumentField.objects.values_list("pk", flat=True)
    for fil in filters:
        document_ids |= WordDocumentField.objects.values_list(fil)

    return DocumentStats.objects.filter(pk__in=document_ids)
