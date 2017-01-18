from djangae.test import TestCase
from djangae.contrib.security.management.commands import dumpurls


class DumpUrlsTests(TestCase):
    def test_dumpurls(self):
        print ("*" * 50) + "\n\n\n"
        """ Test that the `dumpurls` command runs without dying. """
        command = dumpurls.Command()
        command.handle()
