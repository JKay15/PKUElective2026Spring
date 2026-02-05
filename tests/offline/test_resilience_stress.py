#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from collections import OrderedDict
from unittest import mock

from autoelective.course import Course
from autoelective.captcha.captcha import Captcha
from autoelective.exceptions import OperationFailedError, RecognizerError, ElectionFailedError
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self._tree = None
        self.content = b"fake"

    def json(self):
        return self._payload


class _DummyRecognizer:
    def __init__(self):
        self.calls = 0

    def recognize(self, raw):
        self.calls += 1
        if self.calls % 3 == 0:
            raise RecognizerError(msg="mock fail")
        return Captcha("ABCD", None, None, None, None)


class ResilienceStressTest(unittest.TestCase):
    def test_resilience_loop_stress(self):
        # Reduce sleep/backoff for fast test
        loop.MIN_REFRESH_INTERVAL = 0.01
        loop.refresh_interval = 0.01
        loop.refresh_random_deviation = 0.0

        loop.REFRESH_BACKOFF_ENABLE = True
        loop.REFRESH_BACKOFF_FACTOR = 1.2
        loop.REFRESH_BACKOFF_MAX = 0.05
        loop.REFRESH_BACKOFF_THRESHOLD = 1

        loop.FAILURE_NOTIFY_THRESHOLD = 2
        loop.FAILURE_NOTIFY_INTERVAL = 0.01
        loop.FAILURE_COOLDOWN_SECONDS = 0.02
        loop.CRITICAL_COOLDOWN_SECONDS = 0.02

        loop.CLIENT_POOL_RESET_THRESHOLD = 2
        loop.CLIENT_POOL_RESET_COOLDOWN = 0.0
        loop.elective_client_pool_size = 1

        loop.CAPTCHA_PROBE_ENABLED = False
        loop.CAPTCHA_ADAPTIVE_REPORT_INTERVAL = 0
        loop.adaptive.set_enabled(False)
        loop.environ.elective_loop = 0
        loop.goals.clear()
        loop.ignored.clear()

        # Stub notifications
        loop.notify.send_bark_push = lambda *args, **kwargs: None

        # Build a single available course plan
        course = Course("课程A", 1, "学院A", status=(30, 0), href="/supplement/electSupplement.do?x=1")
        courses = OrderedDict([("1", course)])

        orig_tables = loop.get_tables
        orig_courses_detail = loop.get_courses_with_detail
        orig_courses = loop.get_courses

        # Patch config properties
        with mock.patch.object(loop.config.__class__, "courses", new=property(lambda self: courses)), \
             mock.patch.object(loop.config.__class__, "mutexes", new=property(lambda self: OrderedDict())), \
             mock.patch.object(loop.config.__class__, "delays", new=property(lambda self: OrderedDict())):

            # Patch parsers to bypass HTML parsing
            loop.get_tables = lambda _tree: ["plans", "elected"]
            loop.get_courses_with_detail = lambda _tbl: [course]
            loop.get_courses = lambda _tbl: []

            # Patch recognizer
            loop.recognizer = _DummyRecognizer()
            loop._recognizer_names = ["dummy"]
            loop._recognizer_map = {"dummy": loop.recognizer}
            loop.recognizers = [loop.recognizer]
            loop.recognizer_index = 0

            # Patch ElectiveClient methods to avoid network
            call_state = {"supply": 0, "validate": 0}

            def _supply_cancel(self, username, **kwargs):
                call_state["supply"] += 1
                if call_state["supply"] <= 3:
                    raise OperationFailedError(msg="mock supply fail")
                return _DummyResp()

            def _draw(self, **kwargs):
                return _DummyResp()

            def _validate(self, username, code, **kwargs):
                call_state["validate"] += 1
                # alternate valid/invalid
                valid = "2" if call_state["validate"] % 2 == 0 else "0"
                return _DummyResp({"valid": valid})

            def _elect(self, href, **kwargs):
                raise ElectionFailedError(msg="mock elect fail")

            with mock.patch("autoelective.elective.ElectiveClient.get_SupplyCancel", new=_supply_cancel), \
                 mock.patch("autoelective.elective.ElectiveClient.get_DrawServlet", new=_draw), \
                 mock.patch("autoelective.elective.ElectiveClient.get_Validate", new=_validate), \
                 mock.patch("autoelective.elective.ElectiveClient.get_ElectSupplement", new=_elect):

                # Ensure fresh pools with logged-in clients
                orig_make_client = loop._make_client
                try:
                    def _make_client_logged(cid, *args, **kwargs):
                        c = orig_make_client(cid, *args, **kwargs)
                        c._session.cookies.set("a", "b")
                        c.set_expired_time(-1)
                        return c

                    loop._make_client = _make_client_logged

                    loop._client_generation = 0
                    loop._last_pool_reset_at = 0.0
                    loop._reset_client_pool("test_init", force=True)

                    # Run loop in thread and stop after N iterations
                    target_loops = 8

                    def _runner():
                        loop.run_elective_loop()

                    t = threading.Thread(target=_runner)
                    t.daemon = True
                    t.start()

                    start = time.time()
                    while loop.environ.elective_loop < target_loops and time.time() - start < 5.0:
                        time.sleep(0.01)

                    # stop loop by clearing goals
                    loop.goals.clear()
                    loop.ignored.clear()
                    # wait for exit
                    t.join(timeout=5.0)

                    self.assertFalse(t.is_alive(), "run_elective_loop did not stop")
                    # ensure pool reset happened at least once beyond init
                    self.assertGreaterEqual(loop._client_generation, 1)
                finally:
                    loop._make_client = orig_make_client
                    loop.get_tables = orig_tables
                    loop.get_courses_with_detail = orig_courses_detail
                    loop.get_courses = orig_courses


if __name__ == "__main__":
    unittest.main()
