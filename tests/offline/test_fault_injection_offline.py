#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from unittest import mock

from requests.exceptions import RequestException

from autoelective.course import Course
from autoelective.captcha.captcha import Captcha
from autoelective.exceptions import OperationFailedError, OperationTimeoutError, ElectionFailedError
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self._tree = None
        self.content = b"fake"

    def json(self):
        return self._payload


class _BadJsonResp(_DummyResp):
    def json(self):
        raise ValueError("bad json")


class _FaultyRecognizer:
    def __init__(self):
        self.calls = 0

    def recognize(self, raw):
        self.calls += 1
        if self.calls == 1:
            raise OperationFailedError(msg="mock recog fail")
        return Captcha("ABCD", None, None, None, None)


class FaultInjectionOfflineTest(unittest.TestCase):
    def test_fault_injection_schedule(self):
        # Tighten intervals and thresholds for fast test + deterministic backoff
        orig = {
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
            "REFRESH_BACKOFF_ENABLE": loop.REFRESH_BACKOFF_ENABLE,
            "REFRESH_BACKOFF_FACTOR": loop.REFRESH_BACKOFF_FACTOR,
            "REFRESH_BACKOFF_MAX": loop.REFRESH_BACKOFF_MAX,
            "REFRESH_BACKOFF_THRESHOLD": loop.REFRESH_BACKOFF_THRESHOLD,
            "CLIENT_POOL_RESET_THRESHOLD": loop.CLIENT_POOL_RESET_THRESHOLD,
            "CLIENT_POOL_RESET_COOLDOWN": loop.CLIENT_POOL_RESET_COOLDOWN,
            "elective_client_pool_size": loop.elective_client_pool_size,
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
            "CAPTCHA_ADAPTIVE_REPORT_INTERVAL": loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL,
            "adaptive_enabled": loop.adaptive.enabled,
            "electivePool": loop.electivePool,
            "reloginPool": loop.reloginPool,
            "get_tables": loop.get_tables,
            "get_courses_with_detail": loop.get_courses_with_detail,
            "get_courses": loop.get_courses,
        }

        loop.MIN_REFRESH_INTERVAL = 0.01
        loop.refresh_interval = 0.01
        loop.refresh_random_deviation = 0.0
        loop.REFRESH_BACKOFF_ENABLE = True
        loop.REFRESH_BACKOFF_FACTOR = 2.0
        loop.REFRESH_BACKOFF_MAX = 0.1
        loop.REFRESH_BACKOFF_THRESHOLD = 1
        loop.CLIENT_POOL_RESET_THRESHOLD = 2
        loop.CLIENT_POOL_RESET_COOLDOWN = 0.0
        loop.elective_client_pool_size = 1
        loop.CAPTCHA_PROBE_ENABLED = False
        loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
        loop.adaptive.set_enabled(False)

        loop.environ.runtime_stats.clear()
        loop.environ.runtime_gauges.clear()
        loop.environ.elective_loop = 0
        loop.goals.clear()
        loop.ignored.clear()

        # Build a single available course plan
        course = Course("课程A", 1, "学院A", status=(30, 0), href="/supplement/electSupplement.do?x=1")
        courses = OrderedDict([("1", course)])

        # Fault schedule for SupplyCancel
        call_state = {"supply": 0, "validate": 0}

        def _supply_cancel(self, username, **kwargs):
            call_state["supply"] += 1
            if call_state["supply"] == 1:
                raise RequestException("mock network fail")
            if call_state["supply"] == 2:
                raise OperationTimeoutError(msg="mock timeout")
            return _DummyResp()

        def _draw(self, **kwargs):
            return _DummyResp()

        def _validate(self, username, code, **kwargs):
            call_state["validate"] += 1
            if call_state["validate"] == 1:
                return _BadJsonResp()
            if call_state["validate"] == 2:
                return _DummyResp({"valid": "0"})
            return _DummyResp({"valid": "2"})

        def _elect(self, href, **kwargs):
            raise ElectionFailedError(msg="mock elect fail")

        sleep_calls = []
        orig_sleep = loop.time.sleep

        def _fake_sleep(t):
            sleep_calls.append(t)
            orig_sleep(0.001)

        try:
            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply_cancel), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect), \
                 mock.patch.object(loop, "recognizer", new=_FaultyRecognizer()), \
                 mock.patch.object(loop.time, "sleep", new=_fake_sleep):

                # Patch parsers to bypass HTML parsing
                loop.get_tables = lambda _tree: ["plans", "elected"]
                loop.get_courses_with_detail = lambda _tbl: [course]
                loop.get_courses = lambda _tbl: []

                # Ensure fresh pools with logged-in clients
                orig_make_client = loop._make_client

                def _make_client_logged(cid, *args, **kwargs):
                    c = orig_make_client(cid, *args, **kwargs)
                    c._session.cookies.set("a", "b")
                    c.set_expired_time(-1)
                    return c

                loop._make_client = _make_client_logged
                loop._client_generation = 0
                loop._last_pool_reset_at = 0.0
                loop._reset_client_pool("fault_init", force=True)

                t = threading.Thread(target=loop.run_elective_loop)
                t.daemon = True
                t.start()

                target_loops = 6
                start = time.time()
                while loop.environ.elective_loop < target_loops and time.time() - start < 5.0:
                    time.sleep(0.01)

                loop.goals.clear()
                loop.ignored.clear()
                t.join(timeout=5.0)

                self.assertFalse(t.is_alive(), "run_elective_loop did not stop")

                # Assertions for fault reactions + stats
                self.assertGreaterEqual(loop.environ.runtime_stats.get("pool_reset_count", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("captcha_recognize_error", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("captcha_validate_parse_error", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("captcha_validate_fail", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("captcha_validate_pass", 0), 1)

                # Backoff should increase after consecutive errors
                if sleep_calls:
                    self.assertGreater(max(sleep_calls), min(sleep_calls))

        finally:
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]
            loop.REFRESH_BACKOFF_ENABLE = orig["REFRESH_BACKOFF_ENABLE"]
            loop.REFRESH_BACKOFF_FACTOR = orig["REFRESH_BACKOFF_FACTOR"]
            loop.REFRESH_BACKOFF_MAX = orig["REFRESH_BACKOFF_MAX"]
            loop.REFRESH_BACKOFF_THRESHOLD = orig["REFRESH_BACKOFF_THRESHOLD"]
            loop.CLIENT_POOL_RESET_THRESHOLD = orig["CLIENT_POOL_RESET_THRESHOLD"]
            loop.CLIENT_POOL_RESET_COOLDOWN = orig["CLIENT_POOL_RESET_COOLDOWN"]
            loop.elective_client_pool_size = orig["elective_client_pool_size"]
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]
            loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = orig["CAPTCHA_ADAPTIVE_REPORT_INTERVAL"]
            loop.adaptive.set_enabled(orig["adaptive_enabled"])
            loop.electivePool = orig["electivePool"]
            loop.reloginPool = orig["reloginPool"]
            loop.get_tables = orig["get_tables"]
            loop.get_courses_with_detail = orig["get_courses_with_detail"]
            loop.get_courses = orig["get_courses"]


if __name__ == "__main__":
    unittest.main()
