#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective.parser import get_tree
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, content):
        self.content = content
        self._tree = get_tree(content)


class HtmlParseToleranceOfflineTest(unittest.TestCase):
    def test_safe_parse_returns_false_on_bad_html(self):
        bad_html = b"<html><head><title>test</title></head><body><div>no tables</div></body></html>"
        resp = _DummyResp(bad_html)

        loop.environ.runtime_stats.clear()

        with mock.patch.object(loop, "_dump_respose_content", new=lambda *_args, **_kwargs: None), \
             mock.patch.object(loop.cout, "warning", new=lambda *_args, **_kwargs: None):
            elected, plans, ok = loop._safe_parse_supply_cancel(resp, "unit_test")

        self.assertFalse(ok)
        self.assertEqual(elected, [])
        self.assertEqual(plans, [])
        self.assertGreater(loop.environ.runtime_stats.get("html_parse_error", 0), 0)


if __name__ == "__main__":
    unittest.main()
