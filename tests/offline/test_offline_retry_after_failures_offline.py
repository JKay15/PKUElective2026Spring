#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from unittest import mock

from autoelective.course import Course
from autoelective.captcha.captcha import Captcha
from requests.exceptions import Timeout

from autoelective.exceptions import ElectionSuccess
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


class OfflineRetryAfterFailuresOfflineTest(unittest.TestCase):
    def test_retry_after_offline_recover(self):
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
            "_safe_parse_supply_cancel": loop._safe_parse_supply_cancel,
            "recognizer": loop.recognizer,
            "recognizers": list(loop.recognizers),
            "recognizer_index": loop.recognizer_index,
            "_recognizer_names": list(loop._recognizer_names),
            "_recognizer_map": dict(loop._recognizer_map),
            "OFFLINE_ENABLED": loop.OFFLINE_ENABLED,
            "OFFLINE_ERROR_THRESHOLD": loop.OFFLINE_ERROR_THRESHOLD,
            "OFFLINE_COOLDOWN_SECONDS": loop.OFFLINE_COOLDOWN_SECONDS,
            "OFFLINE_PROBE_INTERVAL": loop.OFFLINE_PROBE_INTERVAL,
            "OFFLINE_PROBE_TIMEOUT": loop.OFFLINE_PROBE_TIMEOUT,
            "OFFLINE_OBSERVE_SECONDS": loop.OFFLINE_OBSERVE_SECONDS,
            "OFFLINE_OBSERVE_MIN_REFRESH": loop.OFFLINE_OBSERVE_MIN_REFRESH,
            "FAILURE_COOLDOWN_SECONDS": loop.FAILURE_COOLDOWN_SECONDS,
            "CLIENT_POOL_RESET_THRESHOLD": loop.CLIENT_POOL_RESET_THRESHOLD,
        }

        loop.MIN_REFRESH_INTERVAL = 0.01
        loop.refresh_interval = 0.01
        loop.refresh_random_deviation = 0.0
        loop.REFRESH_BACKOFF_ENABLE = False
        loop.CAPTCHA_PROBE_ENABLED = False
        loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
        loop.adaptive.set_enabled(False)
        loop.elective_client_pool_size = 1

        loop.OFFLINE_ENABLED = True
        loop.OFFLINE_ERROR_THRESHOLD = 2
        loop.OFFLINE_COOLDOWN_SECONDS = 0.2
        loop.OFFLINE_PROBE_INTERVAL = 0.2
        loop.OFFLINE_PROBE_TIMEOUT = 0.2
        loop.OFFLINE_OBSERVE_SECONDS = 0.4
        loop.OFFLINE_OBSERVE_MIN_REFRESH = 0.1
        loop.FAILURE_COOLDOWN_SECONDS = 0
        loop.CLIENT_POOL_RESET_THRESHOLD = 0

        loop.environ.runtime_stats.clear()
        loop.environ.runtime_gauges.clear()
        loop.environ.errors.clear()
        loop.environ.elective_loop = 0
        loop.goals.clear()
        loop.ignored.clear()

        course = Course("课程A", 1, "学院A", status=(2, 1), href="/supplement/electSupplement.do?x=1")
        courses = OrderedDict([("1", course)])

        elect_calls = {"n": 0}
        done_event = threading.Event()

        def _supply_cancel(self, username, **kwargs):
            return _DummyResp()

        draw_calls = {"n": 0}

        def _draw(self, **kwargs):
            draw_calls["n"] += 1
            if draw_calls["n"] <= 2:
                raise Timeout("mock timeout")
            return _DummyResp()

        def _validate(self, username, code, **kwargs):
            return _DummyResp({"valid": "2"})

        def _elect(self, href, **kwargs):
            elect_calls["n"] += 1
            done_event.set()
            raise ElectionSuccess(response=_DummyResp(), msg="ok")

        probe_calls = {"n": 0}

        def _offline_probe():
            probe_calls["n"] += 1
            return probe_calls["n"] >= 2

        orig_make_client = loop._make_client

        def _make_client_logged(cid, *args, **kwargs):
            c = orig_make_client(cid, *args, **kwargs)
            c._session.cookies.set("a", "b")
            c.set_expired_time(-1)
            return c

        try:
            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply_cancel), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect), \
                 mock.patch.object(loop, "_offline_health_probe", new=_offline_probe):

                loop.get_tables = lambda _tree: ["plans", "elected"]
                loop.get_courses_with_detail = lambda _tbl: [course]
                loop.get_courses = lambda _tbl: []
                loop._safe_parse_supply_cancel = lambda _r, _ctx: ([], [course], True)

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

                start = time.time()
                while not done_event.is_set() and time.time() - start < 5.0:
                    time.sleep(0.05)

                loop.goals.clear()
                loop.ignored.clear()
                t.join(timeout=5.0)

                self.assertFalse(t.is_alive(), "run_elective_loop did not stop")
                self.assertTrue(done_event.is_set(), "success event not triggered")
                self.assertGreaterEqual(elect_calls["n"], 1)
                self.assertNotIn(course.to_simplified(), loop.ignored)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("offline_enter", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("offline_recover", 0), 1)
                self.assertGreaterEqual(loop.environ.runtime_stats.get("net_error_timeout", 0), 2)
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
            loop._safe_parse_supply_cancel = orig["_safe_parse_supply_cancel"]
            loop.recognizer = orig["recognizer"]
            loop.recognizers = orig["recognizers"]
            loop.recognizer_index = orig["recognizer_index"]
            loop._recognizer_names = orig["_recognizer_names"]
            loop._recognizer_map = orig["_recognizer_map"]
            loop._make_client = orig_make_client
            loop.OFFLINE_ENABLED = orig["OFFLINE_ENABLED"]
            loop.OFFLINE_ERROR_THRESHOLD = orig["OFFLINE_ERROR_THRESHOLD"]
            loop.OFFLINE_COOLDOWN_SECONDS = orig["OFFLINE_COOLDOWN_SECONDS"]
            loop.OFFLINE_PROBE_INTERVAL = orig["OFFLINE_PROBE_INTERVAL"]
            loop.OFFLINE_PROBE_TIMEOUT = orig["OFFLINE_PROBE_TIMEOUT"]
            loop.OFFLINE_OBSERVE_SECONDS = orig["OFFLINE_OBSERVE_SECONDS"]
            loop.OFFLINE_OBSERVE_MIN_REFRESH = orig["OFFLINE_OBSERVE_MIN_REFRESH"]
            loop.FAILURE_COOLDOWN_SECONDS = orig["FAILURE_COOLDOWN_SECONDS"]
            loop.CLIENT_POOL_RESET_THRESHOLD = orig["CLIENT_POOL_RESET_THRESHOLD"]


if __name__ == "__main__":
    unittest.main()
