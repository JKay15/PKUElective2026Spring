#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective import parser
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, html):
        self.content = html.encode("utf-8")
        self._tree = parser.get_tree(html)


class SupplyCancelSafeParseSuccessOfflineTest(unittest.TestCase):
    def test_safe_parse_supply_cancel_success_realistic_headers(self):
        # This mimics real SupplyCancel datagrid headers (many columns) while still
        # being fully offline/deterministic.
        html = (
            "<html><head><title>补选退选</title></head><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>课程类别</th><th>学分</th><th>周学时</th><th>教师</th>"
            "<th>班号</th><th>开课单位</th><th>专业</th><th>年级</th><th>上课信息</th>"
            "<th>授课语言</th><th>限数/已选</th><th>补选</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>课程A</td><td>通选</td><td>2</td><td>2</td><td>老师A</td>"
            "<td>01</td><td>学院A</td><td></td><td></td><td></td>"
            "<td></td><td>80 / 73</td>"
            "<td><a href='/supplement/electSupplement.do?course=1'>补选</a></td>"
            "</tr>"
            "</table>"
            "<table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>课程类别</th><th>学分</th><th>周学时</th><th>教师</th>"
            "<th>班号</th><th>开课单位</th><th>专业</th><th>年级</th><th>上课信息</th>"
            "<th>限数/已选</th><th>退选</th>"
            "</tr>"
            "<tr class='datagrid-even'>"
            "<td>课程B</td><td>通选</td><td>2</td><td>2</td><td>老师B</td>"
            "<td>02</td><td>学院B</td><td></td><td></td><td></td>"
            "<td>80 / 80</td><td><a href='/supplement/cancel.do?course=2'>退选</a></td>"
            "</tr>"
            "</table></table>"
            "</body></html>"
        )
        resp = _DummyResp(html)

        loop.environ.runtime_stats.clear()
        orig_streak = loop._html_parse_streak
        loop._html_parse_streak = 2

        try:
            with mock.patch.object(loop, "_dump_respose_content", new=lambda *_args, **_kwargs: None), \
                 mock.patch.object(loop.cout, "warning", new=lambda *_args, **_kwargs: None):
                elected, plans, ok = loop._safe_parse_supply_cancel(resp, "unit_test")

            self.assertTrue(ok)
            self.assertEqual(loop.environ.runtime_stats.get("html_parse_error", 0), 0)
            self.assertEqual(loop._html_parse_streak, 0)

            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0].name, "课程A")
            self.assertEqual(plans[0].class_no, 1)
            self.assertEqual(plans[0].school, "学院A")
            self.assertEqual(plans[0].max_quota, 80)
            self.assertEqual(plans[0].used_quota, 73)
            self.assertIn("electSupplement.do", plans[0].href or "")

            self.assertEqual(len(elected), 1)
            self.assertEqual(elected[0].name, "课程B")
            self.assertEqual(elected[0].class_no, 2)
            self.assertEqual(elected[0].school, "学院B")
        finally:
            loop._html_parse_streak = orig_streak


if __name__ == "__main__":
    unittest.main()

