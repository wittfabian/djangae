

from djangae.test import TestCase
from djangae.contrib import search

from .document import Document
from .index import Index


class QueryStringParseTests(TestCase):
    pass


class DocumentTests(TestCase):
    def test_get_fields(self):

        class DocOne(Document):
            pass

        class DocTwo(Document):
            text = search.TextField()
            atom = search.AtomField()

        doc = DocOne()
        self.assertEqual(doc.get_fields(), {})

        doc2 = DocTwo()
        self.assertEqual(2, len(doc2.get_fields()))


class IndexingTests(TestCase):
    def test_indexing_text_fields(self):
        class Doc(Document):
            text = search.TextField()

        doc = Doc(text="This is a test. Cheese.")
        doc2 = Doc(text="This is also a test. Pickle.")

        index = Index(name="My Index")
        index.add(doc)
        index.add(doc2)

        # We should have some generated IDs now
        self.assertTrue(doc.id)
        self.assertTrue(doc2.id)

        results = [x for x in index.search("test")]

        # Both documents should have come back
        self.assertCountEqual(
            [doc.id, doc2.id],
            [x.id for x in results]
        )

        results = [x for x in index.search("TEST")]

        # Both documents should have come back
        self.assertCountEqual(
            [doc.id, doc2.id],
            [x.id for x in results]
        )

        results = [x for x in index.search("cheese OR pickle")]

        # Both documents should have come back
        self.assertCountEqual(
            [doc.id, doc2.id],
            [x.id for x in results]
        )

        results = [x for x in index.search('cheese OR text:pickle')]

        # Both documents should have come back
        self.assertCountEqual(
            [doc.id, doc2.id],
            [x.id for x in results]
        )

        # FIXME: Exact matching
        # results = [x for x in index.search('"cheese" OR pickle')]

        # Both documents should have come back
        # self.assertCountEqual(
        #   [doc.id, doc2.id],
        #   [x.id for x in results]
        # )
