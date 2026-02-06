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
from autoelective.exceptions import RecognizerError
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None, content=b"fake"):
        self._payload = payload or {}
        self.content = content
        self._tree = None

    def json(self):
        return self._payload


class _FailRecognizer:
    def recognize(self, _raw):
        raise RecognizerError(msg="mock recognize fail")


class _OkRecognizer:
    def recognize(self, _raw):
        return Captcha("ABCD", None, None, None, None)


class CaptchaChainPolicyOfflineTest(unittest.TestCase):
    def test_degrade_rotation_and_notify_throttle_unit(self):
        orig = {
            "CAPTCHA_DEGRADE_FAILURES": loop.CAPTCHA_DEGRADE_FAILURES,
            "CAPTCHA_DEGRADE_COOLDOWN": loop.CAPTCHA_DEGRADE_COOLDOWN,
            "CAPTCHA_SWITCH_ON_DEGRADE": loop.CAPTCHA_SWITCH_ON_DEGRADE,
            "CAPTCHA_DEGRADE_NOTIFY": loop.CAPTCHA_DEGRADE_NOTIFY,
            "CAPTCHA_DEGRADE_NOTIFY_INTERVAL": loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL,
            "_captcha_failure_count": loop._captcha_failure_count,
            "_captcha_degrade_until": loop._captcha_degrade_until,
            "_last_degrade_notify_at": loop._last_degrade_notify_at,
            "recognizers": list(loop.recognizers),
            "recognizer": loop.recognizer,
            "recognizer_index": loop.recognizer_index,
            "_recognizer_names": list(loop._recognizer_names),
            "_recognizer_map": dict(loop._recognizer_map),
            "notify_send": loop.notify.send_bark_push,
        }
        try:
            loop.CAPTCHA_DEGRADE_FAILURES = 2
            loop.CAPTCHA_DEGRADE_COOLDOWN = 10
            loop.CAPTCHA_SWITCH_ON_DEGRADE = True
            loop.CAPTCHA_DEGRADE_NOTIFY = True
            loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL = 60

            r1 = _FailRecognizer()
            r2 = _OkRecognizer()
            loop.recognizers = [r1, r2]
            loop._recognizer_names = ["r1", "r2"]
            loop._recognizer_map = {"r1": r1, "r2": r2}
            loop.recognizer_index = 0
            loop.recognizer = r1

            loop._captcha_failure_count = 0
            loop._captcha_degrade_until = 0.0
            loop._last_degrade_notify_at = 0.0

            calls = []

            def _send(msg=None, prefix=None, **_kw):
                calls.append((msg, prefix))

            loop.notify.send_bark_push = _send

            with mock.patch.object(loop.time, "time", new=lambda: 1000.0):
                loop._record_captcha_failure()
                self.assertFalse(loop._captcha_is_degraded())
                self.assertEqual(loop._captcha_failure_count, 1)
                self.assertEqual(loop.recognizer_index, 0)
                self.assertEqual(len(calls), 0)

                loop._record_captcha_failure()
                self.assertTrue(loop._captcha_is_degraded())
                self.assertEqual(loop.recognizer_index, 1)
                self.assertEqual(len(calls), 1)

                # throttled: same timestamp, within interval
                loop._notify_degraded("Captcha degraded again")
                self.assertEqual(len(calls), 1)

            with mock.patch.object(loop.time, "time", new=lambda: 1015.0):
                self.assertFalse(loop._captcha_is_degraded())
        finally:
            loop.CAPTCHA_DEGRADE_FAILURES = orig["CAPTCHA_DEGRADE_FAILURES"]
            loop.CAPTCHA_DEGRADE_COOLDOWN = orig["CAPTCHA_DEGRADE_COOLDOWN"]
            loop.CAPTCHA_SWITCH_ON_DEGRADE = orig["CAPTCHA_SWITCH_ON_DEGRADE"]
            loop.CAPTCHA_DEGRADE_NOTIFY = orig["CAPTCHA_DEGRADE_NOTIFY"]
            loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL = orig["CAPTCHA_DEGRADE_NOTIFY_INTERVAL"]
            loop._captcha_failure_count = orig["_captcha_failure_count"]
            loop._captcha_degrade_until = orig["_captcha_degrade_until"]
            loop._last_degrade_notify_at = orig["_last_degrade_notify_at"]
            loop.recognizers = orig["recognizers"]
            loop.recognizer = orig["recognizer"]
            loop.recognizer_index = orig["recognizer_index"]
            loop._recognizer_names = orig["_recognizer_names"]
            loop._recognizer_map = orig["_recognizer_map"]
            loop.notify.send_bark_push = orig["notify_send"]

    def test_monitor_only_skips_draw_and_elect_in_loop(self):
        orig = {
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
            "REFRESH_BACKOFF_ENABLE": loop.REFRESH_BACKOFF_ENABLE,
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
            "CAPTCHA_ADAPTIVE_REPORT_INTERVAL": loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL,
            "adaptive_enabled": loop.adaptive.enabled,
            "CAPTCHA_DEGRADE_MONITOR_ONLY": loop.CAPTCHA_DEGRADE_MONITOR_ONLY,
            "CAPTCHA_DEGRADE_NOTIFY": loop.CAPTCHA_DEGRADE_NOTIFY,
            "CAPTCHA_DEGRADE_NOTIFY_INTERVAL": loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL,
            "_captcha_degrade_until": loop._captcha_degrade_until,
            "_last_degrade_notify_at": loop._last_degrade_notify_at,
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

            loop.CAPTCHA_DEGRADE_MONITOR_ONLY = True
            loop.CAPTCHA_DEGRADE_NOTIFY = True
            loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL = 0
            loop._last_degrade_notify_at = 0.0
            loop._captcha_degrade_until = time.time() + 60.0

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

            courses = OrderedDict([("1", Course("课程A", 1, "学院A"))])
            available = Course(
                "课程A",
                1,
                "学院A",
                status=(10, 9),
                href="/supplement/electSupplement.do?x=1",
            )

            calls = {"supply": 0, "draw": 0, "validate": 0, "elect": 0}
            notify_msgs = []

            def _supply(self, _username, **_kwargs):
                calls["supply"] += 1
                return _DummyResp()

            def _draw(self, **_kwargs):
                calls["draw"] += 1
                return _DummyResp(content=b"\x89PNG\r\n\x1a\nFAKE")

            def _validate(self, _username, _code, **_kwargs):
                calls["validate"] += 1
                return _DummyResp({"valid": "2"})

            def _elect(self, _href, **_kwargs):
                calls["elect"] += 1
                return _DummyResp()

            def _safe_parse(_resp, _context):
                return [], [available], True

            orig_make_client = loop._make_client

            def _make_client_logged(cid, *args, **kwargs):
                c = orig_make_client(cid, *args, **kwargs)
                c._session.cookies.set("a", "b")
                c.set_expired_time(-1)
                return c

            loop.notify.send_bark_push = (
                lambda msg=None, prefix=None, **_kw: notify_msgs.append(msg or "")
            )

            t = threading.Thread(target=loop.run_elective_loop, name="ElectiveLoopTest")
            t.daemon = True

            with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
                 mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())), \
                 mock.patch.object(loop, "_safe_parse_supply_cancel", new=_safe_parse), \
                 mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect), \
                 mock.patch.object(loop, "_make_client", new=_make_client_logged):
                t.start()
                start = time.time()
                while loop.environ.elective_loop < 2 and (time.time() - start) < 3.0:
                    time.sleep(0.01)
                loop.goals.clear()
                loop.ignored.clear()
                t.join(timeout=3.0)

            self.assertFalse(t.is_alive(), "run_elective_loop did not stop")
            self.assertGreaterEqual(calls["supply"], 1)
            self.assertEqual(calls["draw"], 0)
            self.assertEqual(calls["validate"], 0)
            self.assertEqual(calls["elect"], 0)
            self.assertTrue(any("Available (degraded)" in (m or "") for m in notify_msgs))
        finally:
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]
            loop.REFRESH_BACKOFF_ENABLE = orig["REFRESH_BACKOFF_ENABLE"]
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]
            loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = orig["CAPTCHA_ADAPTIVE_REPORT_INTERVAL"]
            loop.adaptive.set_enabled(orig["adaptive_enabled"])
            loop.CAPTCHA_DEGRADE_MONITOR_ONLY = orig["CAPTCHA_DEGRADE_MONITOR_ONLY"]
            loop.CAPTCHA_DEGRADE_NOTIFY = orig["CAPTCHA_DEGRADE_NOTIFY"]
            loop.CAPTCHA_DEGRADE_NOTIFY_INTERVAL = orig["CAPTCHA_DEGRADE_NOTIFY_INTERVAL"]
            loop._captcha_degrade_until = orig["_captcha_degrade_until"]
            loop._last_degrade_notify_at = orig["_last_degrade_notify_at"]
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

