from gcloudc.db import transaction

from .document import Document


class Index(object):

    def __init__(self, name):
        from .models import IndexStats  # Prevent import too early

        self.name = name
        self.index, created = IndexStats.objects.get_or_create(
            name=name
        )

    @property
    def id(self):
        return self.index.pk if self.index else None

    def add(self, document_or_documents):
        from .models import (  # Prevent import too early
            DocumentData,
            WordFieldIndex,
        )

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

                if tokens is None:
                    # Nothing to index
                    continue

                for token in tokens:
                    token = field.clean_token(token)
                    if token is None:
                        continue

                    # FIXME: Update occurrances
                    with transaction.atomic():
                        obj, updated = WordFieldIndex.objects.update_or_create(
                            document_data_id=document.id,
                            index_stats=self.index,
                            word=token,
                            field_name=field.attname
                        )

                        data.refresh_from_db()
                        data.word_field_indexes.add(obj)
                        data.save()

    def remove(self, document_or_documents):
        pass

    def get(self, document_id):
        pass

    def search(self, query_string, limit=1000):
        from .query import build_document_queryset
        qs = build_document_queryset(query_string, self)[:limit]

        for document in qs:
            yield Document(_document_data=document)
