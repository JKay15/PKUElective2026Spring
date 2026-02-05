#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import unittest

from requests.exceptions import Timeout, SSLError, ConnectionError

import autoelective.loop as loop


class NetworkErrorClassificationTest(unittest.TestCase):
    def test_timeout(self):
        e = Timeout("timeout")
        self.assertEqual(loop._classify_network_error(e), "timeout")

    def test_tls(self):
        e = SSLError("SSL handshake failed")
        self.assertEqual(loop._classify_network_error(e), "tls")

    def test_dns(self):
        e = ConnectionError("Name or service not known")
        self.assertEqual(loop._classify_network_error(e), "dns")

    def test_conn(self):
        e = ConnectionError("connection reset")
        self.assertEqual(loop._classify_network_error(e), "conn")

    def test_dns_gaierror(self):
        e = socket.gaierror(8, "nodename nor servname provided")
        self.assertEqual(loop._classify_network_error(e), "dns")


if __name__ == "__main__":
    unittest.main()
