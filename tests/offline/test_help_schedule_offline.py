#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from datetime import datetime

from autoelective import parser
import autoelective.loop as loop


class HelpScheduleOfflineTest(unittest.TestCase):
    def test_parse_cn_dt_and_schedule(self):
        now_ts = datetime(2026, 2, 5, 0, 0, 0).timestamp()

        ts = loop._parse_cn_dt("2月27日下午15:00", now_ts=now_ts)
        self.assertIsNotNone(ts)
        self.assertEqual(datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"), "2026-02-27 15:00")

        html = (
            "<html><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>选课阶段</th><th>开始时间</th><th>结束时间</th><th>备注</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>维护选课计划</td><td></td><td></td><td></td>"
            "</tr>"
            "<tr class='datagrid-even'>"
            "<td>补退选第一阶段候补选课</td>"
            "<td>2月27日下午15:00</td><td>2月28日上午10:00</td><td></td>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>补退选第二阶段候补选课</td>"
            "<td>3月1日上午9:00</td><td>3月2日上午10:00</td><td></td>"
            "</tr>"
            "</table></table>"
            "</body></html>"
        )

        tree = parser.get_tree(html)
        items = loop._parse_help_schedule(tree, now_ts=now_ts)
        self.assertEqual(len(items), 2)
        self.assertTrue(all("维护" not in (it.get("name") or "") for it in items))
        self.assertTrue(any("补退选" in (it.get("name") or "") for it in items))

        nxt = loop._find_next_operation_start(now_ts, items)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt["name"], "补退选第一阶段候补选课")


if __name__ == "__main__":
    unittest.main()
