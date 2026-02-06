#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from queue import Queue
from unittest import mock

from autoelective.course import Course
from autoelective.captcha.captcha import Captcha
from autoelective.exceptions import QuotaLimitedError
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None, content=b"fake"):
        self._payload = payload or {}
        self.content = content
        self._tree = None

    def json(self):
        return self._payload


class _DummyRecognizer:
    def recognize(self, raw):
        return Captcha("ABCD", None, None, None, None)


class RequestBudgetOfflineTest(unittest.TestCase):
    def _run_loop_for(self, target_loops, timeout_s=3.0):
        t = threading.Thread(target=loop.run_elective_loop, name="ElectiveLoopTest")
        t.daemon = True
        t.start()
        start = time.time()
        while loop.environ.elective_loop < target_loops and (time.time() - start) < timeout_s:
            time.sleep(0.01)
        # stop loop by clearing tasks
        loop.goals.clear()
        loop.ignored.clear()
        t.join(timeout=timeout_s)
        self.assertFalse(t.is_alive(), "run_elective_loop did not stop")

    def test_no_availability_no_captcha_requests(self):
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
            "probePool": getattr(loop, "probePool", None),
            "_probe_pool_shared": getattr(loop, "_probe_pool_shared", False),
            "notify_send": loop.notify.send_bark_push,
            "elective_loop": loop.environ.elective_loop,
        }
        try:
            # Keep the loop fast.
            loop.MIN_REFRESH_INTERVAL = 0.001
            loop.refresh_interval = 0.001
            loop.refresh_random_deviation = 0.0
            loop.REFRESH_BACKOFF_ENABLE = False
            loop.CAPTCHA_PROBE_ENABLED = False
            loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
            loop.adaptive.set_enabled(False)
            loop.environ.elective_loop = 0
            loop.environ.runtime_stats.clear()
            loop.environ.runtime_gauges.clear()
            loop.goals.clear()
            loop.ignored.clear()

            # Isolate pools for test.
            loop.elective_client_pool_size = 1
            loop.electivePool = Queue(maxsize=10)
            loop.reloginPool = Queue(maxsize=10)
            loop.probePool = None
            loop._probe_pool_shared = False

            # Stub notifications.
            loop.notify.send_bark_push = lambda *args, **kwargs: None

            # Provide one configured course.
            courses = OrderedDict([("1", Course("课程A", 1, "学院A"))])

            unavailable = Course(
                "课程A",
                1,
                "学院A",
                status=(10, 10),
                href="/supplement/electSupplement.do?x=1",
            )

            calls = {"supply": 0, "draw": 0, "validate": 0, "elect": 0}

            def _supply(self, _username, **kwargs):
                calls["supply"] += 1
                return _DummyResp()

            def _draw(self, **kwargs):
                calls["draw"] += 1
                return _DummyResp()

            def _validate(self, _username, _code, **kwargs):
                calls["validate"] += 1
                return _DummyResp({"valid": "2"})

            def _elect(self, _href, **kwargs):
                calls["elect"] += 1
                raise QuotaLimitedError(msg="mock quota")

            def _safe_parse(_resp, _context):
                # No available seats: should NOT trigger captcha burst.
                return [], [unavailable], True

            orig_make_client = loop._make_client

            def _make_client_logged(cid, *args, **kwargs):
                c = orig_make_client(cid, *args, **kwargs)
                c._session.cookies.set("a", "b")
                c.set_expired_time(-1)
                return c

            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop, "_safe_parse_supply_cancel", new=_safe_parse), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect), \
                 mock.patch.object(loop, "recognizer", new=_DummyRecognizer()), \
                 mock.patch.object(loop, "_make_client", new=_make_client_logged):
                self._run_loop_for(target_loops=5, timeout_s=3.0)

            self.assertGreaterEqual(calls["supply"], 1)
            self.assertEqual(calls["draw"], 0)
            self.assertEqual(calls["validate"], 0)
            self.assertEqual(calls["elect"], 0)
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
            loop.probePool = orig["probePool"]
            loop._probe_pool_shared = orig["_probe_pool_shared"]
            loop.notify.send_bark_push = orig["notify_send"]
            loop.environ.elective_loop = orig["elective_loop"]
            loop.goals.clear()
            loop.ignored.clear()

    def test_available_once_triggers_single_burst(self):
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
            "probePool": getattr(loop, "probePool", None),
            "_probe_pool_shared": getattr(loop, "_probe_pool_shared", False),
            "notify_send": loop.notify.send_bark_push,
            "elective_loop": loop.environ.elective_loop,
        }
        try:
            loop.MIN_REFRESH_INTERVAL = 0.001
            loop.refresh_interval = 0.001
            loop.refresh_random_deviation = 0.0
            loop.REFRESH_BACKOFF_ENABLE = False
            loop.CAPTCHA_PROBE_ENABLED = False
            loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
            loop.adaptive.set_enabled(False)
            loop.environ.elective_loop = 0
            loop.environ.runtime_stats.clear()
            loop.environ.runtime_gauges.clear()
            loop.goals.clear()
            loop.ignored.clear()

            loop.elective_client_pool_size = 1
            loop.electivePool = Queue(maxsize=10)
            loop.reloginPool = Queue(maxsize=10)
            loop.probePool = None
            loop._probe_pool_shared = False

            loop.notify.send_bark_push = lambda *args, **kwargs: None

            courses = OrderedDict([("1", Course("课程A", 1, "学院A"))])

            available = Course(
                "课程A",
                1,
                "学院A",
                status=(10, 9),
                href="/supplement/electSupplement.do?x=1",
            )
            unavailable = Course(
                "课程A",
                1,
                "学院A",
                status=(10, 10),
                href="/supplement/electSupplement.do?x=1",
            )

            calls = {"supply": 0, "draw": 0, "validate": 0, "elect": 0}

            def _supply(self, _username, **kwargs):
                calls["supply"] += 1
                return _DummyResp()

            def _draw(self, **kwargs):
                calls["draw"] += 1
                return _DummyResp(content=b"\x89PNG\r\n\x1a\nFAKE")

            def _validate(self, _username, _code, **kwargs):
                calls["validate"] += 1
                return _DummyResp({"valid": "2"})

            def _elect(self, _href, **kwargs):
                calls["elect"] += 1
                raise QuotaLimitedError(msg="mock quota")

            state = {"n": 0}

            def _safe_parse(_resp, _context):
                state["n"] += 1
                if state["n"] == 1:
                    return [], [available], True
                return [], [unavailable], True

            orig_make_client = loop._make_client

            def _make_client_logged(cid, *args, **kwargs):
                c = orig_make_client(cid, *args, **kwargs)
                c._session.cookies.set("a", "b")
                c.set_expired_time(-1)
                return c

            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop, "_safe_parse_supply_cancel", new=_safe_parse), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect), \
                 mock.patch.object(loop, "recognizer", new=_DummyRecognizer()), \
                 mock.patch.object(loop, "_make_client", new=_make_client_logged):
                self._run_loop_for(target_loops=3, timeout_s=3.0)

            self.assertGreaterEqual(calls["supply"], 1)
            self.assertEqual(calls["draw"], 1)
            self.assertEqual(calls["validate"], 1)
            self.assertEqual(calls["elect"], 1)
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
            loop.probePool = orig["probePool"]
            loop._probe_pool_shared = orig["_probe_pool_shared"]
            loop.notify.send_bark_push = orig["notify_send"]
            loop.environ.elective_loop = orig["elective_loop"]
            loop.goals.clear()
            loop.ignored.clear()


if __name__ == "__main__":
    unittest.main()
