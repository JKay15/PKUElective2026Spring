#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from unittest import mock

from autoelective.course import Course
from autoelective import parser
import autoelective.loop as loop


class _HtmlResp:
    def __init__(self, html):
        self.text = html
        self.content = html.encode("utf-8")
        self._tree = parser.get_tree(html)


class SupplementPageRetryOfflineTest(unittest.TestCase):
    def test_supplement_page_retry_then_ok(self):
        # Force non-first-page path.
        orig = {
            "supply_cancel_page": loop.supply_cancel_page,
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
            "REFRESH_BACKOFF_ENABLE": loop.REFRESH_BACKOFF_ENABLE,
            "elective_client_pool_size": loop.elective_client_pool_size,
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
        }

        loop.supply_cancel_page = 2
        loop.MIN_REFRESH_INTERVAL = 0.01
        loop.refresh_interval = 0.01
        loop.refresh_random_deviation = 0.0
        loop.REFRESH_BACKOFF_ENABLE = False
        loop.elective_client_pool_size = 1
        loop.CAPTCHA_PROBE_ENABLED = False

        loop.environ.elective_loop = 0
        loop.environ.runtime_stats.clear()
        loop.goals.clear()
        loop.ignored.clear()

        # One goal course must exist in plan_map; make it FULL so we don't go into captcha/elect path.
        course = Course("课程A", 1, "学院A", status=(1, 1), href="/supplement/electSupplement.do?x=1")
        courses = OrderedDict([("1", course)])

        bad_html = "<html><head><title>补选退选</title></head><body><div>empty</div></body></html>"

        good_html = (
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
            "<td>中文</td><td>1 / 1</td><td><a href='/supplement/electSupplement.do?x=1'>刷新</a></td>"
            "</tr>"
            "</table>"
            "<table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>班号</th><th>开课单位</th>"
            "</tr>"
            "<tr class='datagrid-even'>"
            "<td>已选课</td><td>01</td><td>学院A</td>"
            "</tr>"
            "</table></table>"
            "</body></html>"
        )

        calls = {"supp": 0, "supply": 0}

        def _supplement(self, username, page=1, **kwargs):
            calls["supp"] += 1
            # First call returns empty page, second call returns normal page.
            return _HtmlResp(bad_html if calls["supp"] == 1 else good_html)

        def _supply_cancel(self, username, **kwargs):
            calls["supply"] += 1
            return _HtmlResp(good_html)

        # Fast sleep for loop.
        orig_sleep = loop.time.sleep

        def _fake_sleep(_t):
            orig_sleep(0.001)

        try:
            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch("autoelective.elective.ElectiveClient.get_supplement", new=_supplement), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply_cancel), \
                 mock.patch.object(loop.time, "sleep", new=_fake_sleep):

                # Ensure a logged-in client exists in pool
                orig_make = loop._make_client

                def _make_logged(cid, *args, **kwargs):
                    c = orig_make(cid, *args, **kwargs)
                    c._session.cookies.set("a", "b")
                    c.set_expired_time(-1)
                    return c

                loop._make_client = _make_logged
                loop._client_generation = 0
                loop._last_pool_reset_at = 0.0
                loop._reset_client_pool("test_init", force=True)

                t = threading.Thread(target=loop.run_elective_loop)
                t.daemon = True
                t.start()

                # Wait for a few loops to ensure retry path happened.
                start = time.time()
                while loop.environ.elective_loop < 3 and time.time() - start < 5.0:
                    time.sleep(0.01)

                loop.goals.clear()
                loop.ignored.clear()
                t.join(timeout=5.0)

                self.assertFalse(t.is_alive(), "run_elective_loop did not stop")
                self.assertGreaterEqual(calls["supp"], 2)
                self.assertGreaterEqual(calls["supply"], 1, "Should fallback to SupplyCancel once after parse fail")
        finally:
            loop.supply_cancel_page = orig["supply_cancel_page"]
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]
            loop.REFRESH_BACKOFF_ENABLE = orig["REFRESH_BACKOFF_ENABLE"]
            loop.elective_client_pool_size = orig["elective_client_pool_size"]
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]


if __name__ == "__main__":
    unittest.main()

