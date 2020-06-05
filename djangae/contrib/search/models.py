from django.db import models
from gcloudc.db import transaction
from gcloudc.db.models.fields.iterable import (
    ListField,
)

from gcloudc.db.models.fields.related import RelatedSetField

from .document import Document

WORD_DOCUMENT_JOIN_STRING = "|"


class DocumentData(models.Model):
    """
        'Document' is intentionally not a model;
        it would ruin the abstraction, and we need to
        store all kinds of data related to a Document.
        So instead, each Document has an instance of DocumentData
        this is the closest to a database representation of the doc
        and indeed, is where the document ID comes from.

        DocumentData exists to keep a reference to all word indexes
        and any stats/settings about the document (e.g. its rank).
    """
    index_stats = models.ForeignKey("IndexStats", on_delete=models.CASCADE)

    # This allows for up-to 10000 unique terms in a single
    # document. We need this data when deleting a document
    # from the index
    word_indexes = RelatedSetField("WordIndex")


class WordIndex(models.Model):
    # key should be of the format WWWW|XXXX|YYYY|ZZZZ where:
    # WWWW = index ID
    # XXXX = normalised word
    # YYYY = field name
    # ZZZZ = document id

    # Querying for documents or fields containing the word
    # will just be a key__startswith query (effectively)
    id = models.CharField(primary_key=True, max_length=100)

    index_stats = models.ForeignKey("IndexStats", on_delete=models.CASCADE)
    document = models.ForeignKey("Document", on_delete=models.CASCADE)
    word = models.CharField(max_length=500)
    field_name = models.CharField(max_length=500)
    field_content = models.TextField()

    # List of indexes into field content where this word occurs
    # This is used when searching for phrases
    occurrences = ListField(models.IntegerField(), blank=False)

    @property
    def document_id(self):
        return int(self.key.split(WORD_DOCUMENT_JOIN_STRING)[1])

    @property
    def document(self):
        return Document.objects.get(pk=self.document_id)

    def save(self, *args, **kwargs):
        orig_pk = self.pk

        self.pk = WORD_DOCUMENT_JOIN_STRING.join(
            self.index_stats_id, self.word, self.field_name, self.document_id
        )

        # Just check that we didn't *change* the PK
        assert((orig_pk is None) or orig_pk == self.pk)
        super().save(*args, **kwargs)


class IndexStats(models.Model):
    """
        This is a representation of the index
        in the datastore. Its PK is used as
        a prefix to documents and word tables
        but it's only really used itself to maintain
        statistics about the indexed data.
    """

    name = models.CharField(max_length=100, unique=True)
    document_count = models.PositiveIntegerField(default=0)


class Index(object):

    def __init__(self, name):
        self.name = name
        self.index, created = IndexStats.objects.get_or_create(
            name=name
        )

    def add(self, document_or_documents):
        if isinstance(document_or_documents, Document):
            documents = [document_or_documents]
        else:
            documents = document_or_documents[:]

        for document in documents:
            # We go through the document fields, pull out the values that have been set
            # then we index them.

            data = document._data

            if data is None:
                # Generate a database representation of this Document
                data = DocumentData.objects.create(index_stats=self.index)
                document._set_data(data)

            assert(document.id)  # This should be a thing by now

            for field_name, field in document.get_fields().items():
                # Get the field value, use the default if it's not set
                value = getattr(document, field.attname, None)
                value = field.default if value is None else value
                value = field.normalize_value(value)

                # Tokenize the value, this will effectively mean lower-casing
                # removing punctuation etc. and returning a list of things
                # to index
                tokens = field.tokenize_value(value)

                for token in tokens:
                    # FIXME: Update occurrances
                    with transaction.atomic():
                        obj, updated = WordIndex.objects.update_or_create(
                            document_id=document.id,
                            index_stats=self.index,
                            word=token,
                            field_name=field.attname,
                            field_content=value
                        )

                        data.refresh_from_db()
                        data.word_indexes.add(obj)
                        data.save()

    def remove(self, document_or_documents):
        pass

    def get(self, document_id):
        pass

    def search(self, query_string, limit=1000):
        from .query import build_document_queryset
        qs = build_document_queryset(query_string)[:limit]

        for document in qs:
            yield Document(document)
