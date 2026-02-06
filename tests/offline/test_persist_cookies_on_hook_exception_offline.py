#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace

from autoelective.exceptions import InvalidTokenError
from autoelective.hook import check_elective_title, with_etree


class _DummyClient(object):
    def __init__(self):
        self.calls = 0

    def persist_cookies(self, r):
        self.calls += 1


class _FakeResponse(object):
    def __init__(self, text: str, client: _DummyClient):
        self.text = text
        self.request = SimpleNamespace(_client=client)


class PersistCookiesOnHookExceptionOfflineTest(unittest.TestCase):
    def test_persist_cookies_called_on_exception(self):
        html = (
            "<html><head><title>系统提示</title></head><body>"
            "<table><table><table><td><strong>出错提示:</strong>token无效</td></table></table></table>"
            "</body></html>"
        )
        client = _DummyClient()
        r = _FakeResponse(text=html, client=client)
        with_etree(r)

        with self.assertRaises(InvalidTokenError):
            check_elective_title(r)

        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()

