#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest import mock

import autoelective.rate_limit as rl
from autoelective.const import ElectiveURL


class RateLimitIntegrationOfflineTest(unittest.TestCase):
    def test_burst_allows_short_burst_without_sleep(self):
        # Fake monotonic clock so the test runs instantly.
        now = {"t": 0.0}
        sleeps = []

        def _mono():
            return now["t"]

        def _sleep(dt):
            dt = float(dt or 0.0)
            sleeps.append(dt)
            now["t"] += dt

        stats = {"sleep": 0, "last": None}

        def _stat_inc(k, d=1):
            if k == "rate_limit_sleep":
                stats["sleep"] += 1

        def _stat_set(k, v):
            if k == "rate_limit_last_sleep":
                stats["last"] = v

        cfg = SimpleNamespace(
            rate_limit_enable=True,
            rate_limit_global_rps=0,
            rate_limit_global_burst=0,
            # Elective host bucket: 1 rps, burst 4 means 4 quick requests (Draw+Validate+Elect+something)
            # will pass without sleep; the 5th should sleep ~1s.
            rate_limit_elective_rps=1.0,
            rate_limit_elective_burst=4.0,
            rate_limit_iaaa_rps=0,
            rate_limit_iaaa_burst=0,
        )

        with mock.patch.object(rl.time, "monotonic", new=_mono), \
             mock.patch.object(rl.time, "sleep", new=_sleep):
            rl.configure(cfg)
            rl.set_stat_hooks(_stat_inc, _stat_set)

            waits = []
            for _ in range(4):
                waits.append(rl.throttle(ElectiveURL.SupplyCancel))
            # No sleep for the burst.
            self.assertEqual(sum(1 for w in waits if w > 0), 0)
            self.assertEqual(sleeps, [])

            w5 = rl.throttle(ElectiveURL.SupplyCancel)
            self.assertGreater(w5, 0.0)
            self.assertGreaterEqual(sum(sleeps), 0.9)
            self.assertGreaterEqual(stats["sleep"], 1)
            self.assertIsNotNone(stats["last"])


if __name__ == "__main__":
    unittest.main()

