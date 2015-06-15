from socket import socket, SHUT_RDWR

from djangae.contrib import sleuth
from djangae.test import TestCase
from djangae.utils import get_next_available_port

class AvailablePortTests(TestCase):

    def test_get_next_available_port(self):
        url = "127.0.0.1"
        port = 8081
        self.assertEquals(8081, get_next_available_port(url, port))
        with sleuth.switch("djangae.utils.port_is_open",
                lambda *args, **kwargs: False if args[1] < 8085 else True):
            self.assertEquals(8085, get_next_available_port(url, port))
