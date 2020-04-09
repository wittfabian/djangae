

from djangae.test import TestCase
from .models import Index


class QueryStringParseTests(TestCase):
    def test_parsing_of_nested_logic_ops(self):
        s = "this:(this AND that) OR NOT that:(that AND this) stuff"

        index = Index("test")
        tokens = index._qs_tokenize_one(s)

        self.assertEqual(
            tokens,
            [
                "this:this AND that",
                "OR",
                "NOT",
                "that:that AND this"
            ]
        )

        branches = index._qs_tokenize_two(tokens)

        self.assertEqual(
            branches,
            ("AND", [
                ("OR", [
                    "this:this AND that",
                    ("NOT", ["that:that AND this"])
                ])
            ])
        )
