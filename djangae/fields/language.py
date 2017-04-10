# encoding: utf-8

import os
import zipfile

from .computed import ComputedFieldMixin
from .charfields import CharField

# pyuca only supports version 5.2.0 of the collation algorithm on Python 2.x
COLLATION_FILE = "allkeys-5.2.0.txt"
COLLATION_ZIP_FILE = os.path.join(os.path.dirname(__file__), "allkeys-5.2.0.zip")


class ZipLoaderMixin(object):
    """
        The UCA collation file is massive (nearly 1.5M) but it's all text
        so it compresses easily. We ship the file zipped up and then decompress
        it on the fly here to save on storage, data transfer, memory etc.

        The use of generators on load should be efficient.
    """

    def __init__(self, zip_filename, text_filename):
        """
            The BaseCollator class __init__ takes a filename and calls
            load(filename). Here we pass up the text filename but store the
            zip filename, then override load so we can load from the zip instead
            of a filesystem.
        """
        self.zip_filename = zip_filename
        super(ZipLoaderMixin, self).__init__(filename=text_filename)

    def load(self, filename):
        from pyuca.collator import COLL_ELEMENT_PATTERN, hexstrings2int # pyuca is required for ComputedCollationField

        with zipfile.ZipFile(self.zip_filename) as z:
            with z.open(filename) as f:
                for line in f:
                    line = line.split("#", 1)[0].rstrip()

                    if not line or line.startswith("@version"):
                        continue

                    a, b = line.split(";", 1)
                    char_list = hexstrings2int(a.split())
                    coll_elements = []
                    for x in COLL_ELEMENT_PATTERN.finditer(b.strip()):
                        weights = x.groups()
                        coll_elements.append(hexstrings2int(weights))
                    self.table.add(char_list, coll_elements)


class ComputedCollationField(ComputedFieldMixin, CharField):
    """
        App Engine sorts strings based on the unicode codepoints that make them
        up. When you have strings from non-ASCII languages this makes the sort order
        incorrect (e.g. Ł will be sorted after Z).

        This field uses the pyuca library to calculate a sort key using the
        Unicode Collation Algorithm, which can then be used for ordering querysets
        correctly.
    """

    collator = None

    def __init__(self, source_field_name):
        import pyuca # Required dependency for ComputedCollationField
        from pyuca.collator import Collator_5_2_0

        # Instantiate Collator once only to save on memory / processing
        if not ComputedCollationField.collator:
            class Collator(ZipLoaderMixin, Collator_5_2_0):
                pass

            ComputedCollationField.collator = Collator(COLLATION_ZIP_FILE, COLLATION_FILE)

        def computer(instance):
            source_value = getattr(instance, source_field_name, u"")
            return self.collator.sort_key(unicode(source_value, "utf-8"))

        super(ComputedCollationField, self).__init__(computer)

    def deconstruct(self):
        name, path, args, kwargs = super(ComputedCollationField, self).deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs

