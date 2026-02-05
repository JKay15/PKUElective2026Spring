#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from unittest import mock

from autoelective.course import Course
from autoelective.captcha.captcha import Captcha
from autoelective.exceptions import ElectionSuccess
from autoelective.rule import Mutex
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self._tree = None
        self.content = b"fake"

    def json(self):
        return self._payload


class _DummyRecognizer:
    def recognize(self, raw):
        return Captcha("ABCD", None, None, None, None)


class MutexPriorityOfflineTest(unittest.TestCase):
    def test_mutex_prevents_lower_priority_elect(self):
        orig = {
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
            "REFRESH_BACKOFF_ENABLE": loop.REFRESH_BACKOFF_ENABLE,
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
            "CAPTCHA_ADAPTIVE_REPORT_INTERVAL": loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL,
            "adaptive_enabled": loop.adaptive.enabled,
            "elective_client_pool_size": loop.elective_client_pool_size,
            "electivePool": loop.electivePool,
            "reloginPool": loop.reloginPool,
            "get_tables": loop.get_tables,
            "get_courses_with_detail": loop.get_courses_with_detail,
            "get_courses": loop.get_courses,
            "recognizer": loop.recognizer,
            "recognizers": list(loop.recognizers),
            "recognizer_index": loop.recognizer_index,
            "_recognizer_names": list(loop._recognizer_names),
            "_recognizer_map": dict(loop._recognizer_map),
        }

        loop.MIN_REFRESH_INTERVAL = 0.01
        loop.refresh_interval = 0.01
        loop.refresh_random_deviation = 0.0
        loop.REFRESH_BACKOFF_ENABLE = False
        loop.CAPTCHA_PROBE_ENABLED = False
        loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
        loop.adaptive.set_enabled(False)
        loop.elective_client_pool_size = 1

        loop.environ.runtime_stats.clear()
        loop.environ.runtime_gauges.clear()
        loop.environ.elective_loop = 0
        loop.goals.clear()
        loop.ignored.clear()

        course_a = Course("课程A", 1, "学院A", status=(1, 0), href="/supplement/electSupplement.do?x=1")
        course_b = Course("课程B", 2, "学院B", status=(1, 0), href="/supplement/electSupplement.do?x=2")
        courses = OrderedDict([("A", course_a), ("B", course_b)])
        mutexes = OrderedDict([("m1", Mutex(["A", "B"]))])

        elect_calls = {"n": 0}
        elected_flag = {"ok": False}
        success_event = threading.Event()

        def _supply_cancel(self, username, **kwargs):
            return _DummyResp()

        def _draw(self, **kwargs):
            return _DummyResp()

        def _validate(self, username, code, **kwargs):
            return _DummyResp({"valid": "2"})

        def _elect(self, href, **kwargs):
            elect_calls["n"] += 1
            if elect_calls["n"] == 1:
                elected_flag["ok"] = True
                success_event.set()
                raise ElectionSuccess(response=_DummyResp(), msg="ok")
            raise RuntimeError("should not attempt second elect")

        orig_make_client = loop._make_client

        def _make_client_logged(cid, *args, **kwargs):
            c = orig_make_client(cid, *args, **kwargs)
            c._session.cookies.set("a", "b")
            c.set_expired_time(-1)
            return c

        try:
            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: mutexes)), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply_cancel), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect):

                loop.get_tables = lambda _tree: ["plans", "elected"]
                loop.get_courses_with_detail = lambda _tbl: [course_a, course_b]
                loop.get_courses = lambda _tbl: [course_a] if elected_flag["ok"] else []

                loop.recognizer = _DummyRecognizer()
                loop._recognizer_names = ["dummy"]
                loop._recognizer_map = {"dummy": loop.recognizer}
                loop.recognizers = [loop.recognizer]
                loop.recognizer_index = 0

                loop._make_client = _make_client_logged
                loop._client_generation = 0
                loop._last_pool_reset_at = 0.0
                loop._reset_client_pool("test_init", force=True)

                t = threading.Thread(target=loop.run_elective_loop)
                t.daemon = True
                t.start()

                success_event.wait(timeout=3.0)
                time.sleep(0.05)
                loop.goals.clear()
                t.join(timeout=5.0)

                self.assertFalse(t.is_alive(), "run_elective_loop did not stop")
                self.assertEqual(elect_calls["n"], 1)
                self.assertIn(course_b.to_simplified(), loop.ignored)
        finally:
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]
            loop.REFRESH_BACKOFF_ENABLE = orig["REFRESH_BACKOFF_ENABLE"]
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]
            loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = orig["CAPTCHA_ADAPTIVE_REPORT_INTERVAL"]
            loop.adaptive.set_enabled(orig["adaptive_enabled"])
            loop.elective_client_pool_size = orig["elective_client_pool_size"]
            loop.electivePool = orig["electivePool"]
            loop.reloginPool = orig["reloginPool"]
            loop.get_tables = orig["get_tables"]
            loop.get_courses_with_detail = orig["get_courses_with_detail"]
            loop.get_courses = orig["get_courses"]
            loop.recognizer = orig["recognizer"]
            loop.recognizers = orig["recognizers"]
            loop.recognizer_index = orig["recognizer_index"]
            loop._recognizer_names = orig["_recognizer_names"]
            loop._recognizer_map = orig["_recognizer_map"]
            loop._make_client = orig_make_client


if __name__ == "__main__":
    unittest.main()
