#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective.course import Course
import autoelective.loop as loop


class OfflineCircuitBreakerTest(unittest.TestCase):
    def test_offline_enter_and_recover(self):
        orig = {
            "OFFLINE_ENABLED": loop.OFFLINE_ENABLED,
            "OFFLINE_ERROR_THRESHOLD": loop.OFFLINE_ERROR_THRESHOLD,
            "OFFLINE_COOLDOWN_SECONDS": loop.OFFLINE_COOLDOWN_SECONDS,
            "OFFLINE_PROBE_INTERVAL": loop.OFFLINE_PROBE_INTERVAL,
            "_offline_active": loop._offline_active,
            "_offline_next_probe_at": loop._offline_next_probe_at,
            "_offline_error_streak": loop._offline_error_streak,
            "goals": list(loop.goals),
            "ignored": dict(loop.ignored),
        }

        loop.OFFLINE_ENABLED = True
        loop.OFFLINE_ERROR_THRESHOLD = 2
        loop.OFFLINE_COOLDOWN_SECONDS = 0
        loop.OFFLINE_PROBE_INTERVAL = 1

        loop._offline_active = False
        loop._offline_next_probe_at = 0.0
        loop._offline_error_streak = 0
        loop.environ.runtime_stats.clear()
        loop.environ.runtime_gauges.clear()

        dummy_course = Course("课程A", 1, "学院A", status=(1, 0), href="/supplement/electSupplement.do?x=1")
        loop.goals.clear()
        loop.ignored.clear()
        loop.goals.append(dummy_course)

        reset_called = {"n": 0}

        def _fake_reset(reason, force=False):
            reset_called["n"] += 1
            return True

        with mock.patch.object(loop, "_offline_health_probe", return_value=True), \
             mock.patch.object(loop, "_reset_client_pool", new=_fake_reset), \
             mock.patch.object(loop.time, "sleep", new=lambda _t: None):
            loop._record_network_error("net")
            self.assertFalse(loop._offline_is_active())
            loop._record_network_error("net")
            self.assertTrue(loop._offline_is_active())

            loop._offline_tick()

        self.assertFalse(loop._offline_is_active())
        self.assertGreaterEqual(loop.environ.runtime_stats.get("offline_enter", 0), 1)
        self.assertGreaterEqual(loop.environ.runtime_stats.get("offline_recover", 0), 1)
        self.assertGreaterEqual(reset_called["n"], 1)

        loop.OFFLINE_ENABLED = orig["OFFLINE_ENABLED"]
        loop.OFFLINE_ERROR_THRESHOLD = orig["OFFLINE_ERROR_THRESHOLD"]
        loop.OFFLINE_COOLDOWN_SECONDS = orig["OFFLINE_COOLDOWN_SECONDS"]
        loop.OFFLINE_PROBE_INTERVAL = orig["OFFLINE_PROBE_INTERVAL"]
        loop._offline_active = orig["_offline_active"]
        loop._offline_next_probe_at = orig["_offline_next_probe_at"]
        loop._offline_error_streak = orig["_offline_error_streak"]
        loop.goals[:] = orig["goals"]
        loop.ignored.clear()
        loop.ignored.update(orig["ignored"])


if __name__ == "__main__":
    unittest.main()
