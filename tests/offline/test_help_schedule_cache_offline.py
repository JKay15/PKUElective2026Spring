#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from autoelective import parser
import autoelective.loop as loop


class _FakeElective:
    def __init__(self, tree):
        self.calls = 0
        self._tree = tree

    def get_HelpController(self):
        self.calls += 1
        return SimpleNamespace(_tree=self._tree)


class HelpScheduleCacheOfflineTest(unittest.TestCase):
    def test_get_help_schedule_cache_and_force_refresh(self):
        now_ts = datetime(2026, 2, 5, 0, 0, 0).timestamp()
        html = (
            "<html><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>选课阶段</th><th>开始时间</th><th>结束时间</th><th>备注</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>补退选第一阶段候补选课</td>"
            "<td>2月27日下午15:00</td><td>2月28日上午10:00</td><td></td>"
            "</tr>"
            "</table></table>"
            "</body></html>"
        )
        fake = _FakeElective(parser.get_tree(html))

        orig = {
            "NOT_IN_OPERATION_DYNAMIC_ENABLE": loop.NOT_IN_OPERATION_DYNAMIC_ENABLE,
            "NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS": loop.NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS,
            "_help_schedule_items": loop._help_schedule_items,
            "_help_schedule_fetched_at": loop._help_schedule_fetched_at,
        }

        try:
            loop.NOT_IN_OPERATION_DYNAMIC_ENABLE = True
            loop.NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS = 3600.0
            loop._help_schedule_items = None
            loop._help_schedule_fetched_at = 0.0

            with mock.patch.object(loop.time, "time", new=lambda: now_ts):
                items1 = loop._get_help_schedule(elective=fake, force_refresh=False)
                items2 = loop._get_help_schedule(elective=fake, force_refresh=False)
                items3 = loop._get_help_schedule(elective=fake, force_refresh=True)

            self.assertEqual(fake.calls, 2)
            self.assertEqual(items1, items2)
            self.assertIsInstance(items1, list)
            self.assertEqual(len(items1), 1)
            self.assertEqual(items1[0]["name"], "补退选第一阶段候补选课")
            self.assertEqual(items3[0]["name"], "补退选第一阶段候补选课")
        finally:
            loop.NOT_IN_OPERATION_DYNAMIC_ENABLE = orig["NOT_IN_OPERATION_DYNAMIC_ENABLE"]
            loop.NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS = orig[
                "NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS"
            ]
            loop._help_schedule_items = orig["_help_schedule_items"]
            loop._help_schedule_fetched_at = orig["_help_schedule_fetched_at"]


if __name__ == "__main__":
    unittest.main()

