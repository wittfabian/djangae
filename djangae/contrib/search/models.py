from django.db import models
from gcloudc.db.models.fields.iterable import ListField


class Document(models.Model):
    index_name = models.CharField(max_length=128)


class WordDocumentField(models.Model):
    # key should be of the format XXXX_YYYY_ZZZZ where:
    # XXXX = normalised word
    # YYYY = document ID
    # ZZZZ = field name

    # Querying for documents or fields containing the word
    # will just be a key__startswith query (effectively)
    id = models.CharField(primary_key=True, max_length=100)

    word = models.CharField(max_length=500)
    field_name = models.CharField(max_length=500)
    field_content = models.TextField()

    # List of indexes into field content where this word occurs
    # This is used when searching for phrases
    occurrences = ListField(models.IntegerField(), blank=False)

    @property
    def document_id(self):
        return int(self.key.split("_")[1])

    @property
    def document(self):
        return Document.objects.get(pk=self.document_id)


class Index(object):

    def __init__(self, index_name):
        self.name = index_name

    def add(self, document_or_documents):
        pass

    def remove(self, document_or_documents):
        pass

    def get(self, document_id):
        pass

    def _qs_tokenize_one(self, query_string):
        """
            First pass. Tokenizes the string into logic-ops
            and field:values
        """

        tokens = []
        brace_counter = 0
        token = ""

        for c in query_string:
            if c == "(":
                brace_counter += 1
                continue
            elif c == ")":
                brace_counter -= 1
                continue

            if not brace_counter:
                # We're not in some braces
                if c == " " and token:
                    tokens.append(token)
                    token = ""
                else:
                    token += c
            else:
                token += c
        else:
            tokens.append(token)

        return tokens

    def _qs_tokenize_two(self, tokens):
        # We now take the tokens resulting from the previous phase
        # and build a node heirarchy of global operators

        # AND takes precedence, let's branch that
        and_branches = []
        branch = []
        for token in tokens:
            if token != "AND":
                branch.append(token)
            else:
                and_branches.append(branch)
                branch = []
        else:
            and_branches.append(branch)

        for and_branch in and_branches:
            branch = []
            new_and_branch = []
            for token in and_branch:
                if token != "OR":
                    branch.append(token)
                else:
                    new_and_branch.append(branch)
                    branch = []
            else:
                new_and_branch.append(branch)

            if len(new_and_branch) == 1:
                and_branch[:] = new_and_branch[0]
            else:
                and_branch[:] = new_and_branch

        return and_branches

    def search(self, query_string, limit=100, only_fields=None):
        # The App Engine Search API is tricky to parse. Essentially though we are going
        # to allow 2 levels of logic operations (e.g. AND, OR, NOT). There's the
        # global level, then the field value level. I dunno if that's how it worked
        # before but that's what we're going with here.

        tokens = self._qs_tokenize_one(query_string)
        print(tokens)
