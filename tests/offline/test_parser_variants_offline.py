#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective.parser import get_tree, get_tables, get_courses_with_detail
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, content):
        self.content = content
        self._tree = get_tree(content)


def _build_supplycancel_html(headers, row_cells):
    ths = "".join("<th>%s</th>" % h for h in headers)
    tds = "".join("<td>%s</td>" % c for c in row_cells)
    html = (
        "<html><head><title>选课</title></head><body>"
        "<table><table class='datagrid'>"
        "<tr class='datagrid-header'>%s</tr>"
        "<tr class='datagrid-odd'>%s</tr>"
        "</table>"
        "<table class='datagrid'>"
        "<tr class='datagrid-header'><th>课程名</th><th>班号</th><th>开课单位</th></tr>"
        "<tr class='datagrid-even'><td>课程B</td><td>02</td><td>学院B</td></tr>"
        "</table></table>"
        "</body></html>"
    ) % (ths, tds)
    return html.encode("utf-8")


class ParserVariantsOfflineTest(unittest.TestCase):
    def test_reordered_columns_still_parses(self):
        # Reorder columns but keep all required fields.
        headers = ["班号", "课程名", "开课单位", "补选", "限数/已选"]
        row = [
            "01",
            "课程A",
            "学院A",
            "<a href='/supplement/electSupplement.do?course=1'>补选</a>",
            "30/10",
        ]
        raw = _build_supplycancel_html(headers, row)
        tree = get_tree(raw)
        tables = get_tables(tree)
        self.assertGreaterEqual(len(tables), 2)
        plans = get_courses_with_detail(tables[0])
        self.assertEqual(len(plans), 1)
        c = plans[0]
        self.assertEqual(c.name, "课程A")
        self.assertEqual(c.class_no, 1)
        self.assertEqual(c.school, "学院A")
        self.assertEqual(c.max_quota, 30)
        self.assertEqual(c.used_quota, 10)
        self.assertIn("electSupplement.do", c.href or "")

    def test_header_whitespace_is_tolerated(self):
        headers = ["  课程名 \n", " 班号", "开课单位  ", "限数/已选", "补选"]
        row = [
            "课程A",
            "01",
            "学院A",
            "30/10",
            "<a href='/supplement/electSupplement.do?course=1'>补选</a>",
        ]
        raw = _build_supplycancel_html(headers, row)
        tree = get_tree(raw)
        tables = get_tables(tree)
        plans = get_courses_with_detail(tables[0])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].name, "课程A")

    def test_missing_required_column_fails_safe_parse(self):
        # Missing "补选" should cause parse to fail and be handled by _safe_parse_supply_cancel.
        headers = ["课程名", "班号", "开课单位", "限数/已选"]
        row = ["课程A", "01", "学院A", "30/10"]
        raw = _build_supplycancel_html(headers, row)
        resp = _DummyResp(raw)

        loop.environ.runtime_stats.clear()
        with mock.patch.object(loop, "_dump_respose_content", new=lambda *_a, **_kw: None), \
             mock.patch.object(loop.cout, "warning", new=lambda *_a, **_kw: None):
            elected, plans, ok = loop._safe_parse_supply_cancel(resp, "variant_missing_col")

        self.assertFalse(ok)
        self.assertEqual(elected, [])
        self.assertEqual(plans, [])
        self.assertGreater(loop.environ.runtime_stats.get("html_parse_error", 0), 0)


if __name__ == "__main__":
    unittest.main()

