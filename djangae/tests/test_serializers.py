import json

from djangae.test import TestCase


class JSONEncoderTestCase(TestCase):
    def test_encodes_sets_as_lists(self):
        # Django's built-in encoder does lists, but not sets. Djangae patches
        # it to make lists from sets, which is needed for SetField.
        from django.core.serializers.json import DjangoJSONEncoder

        encoder = DjangoJSONEncoder()
        obj = {'test': set(['foo', 'bar', 'baz'])}
        data = encoder.encode(obj)
        result = json.loads(data)

        self.assertIsInstance(result['test'], list)
