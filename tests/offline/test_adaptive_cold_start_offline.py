#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from autoelective.captcha.adaptive import CaptchaAdaptiveManager


class AdaptiveColdStartOfflineTest(unittest.TestCase):
    def test_fail_streak_degrade_then_recover(self):
        mgr = CaptchaAdaptiveManager(
            ["a", "b"],
            enabled=True,
            min_samples=5,
            epsilon=0.1,
            update_interval=0,
            fail_streak_degrade=2,
        )

        mgr.record_attempt("a", False, latency=1.0, h_latency=0.5)
        mgr.record_attempt("a", False, latency=1.0, h_latency=0.5)

        order, switch, changed = mgr.maybe_reorder(["a", "b"], loop_count=1)
        self.assertTrue(changed)
        self.assertTrue(switch)
        self.assertEqual(order, ["b", "a"])

        mgr.record_attempt("a", True, latency=0.5, h_latency=0.4)
        order2, switch2, changed2 = mgr.maybe_reorder(order, loop_count=2)
        self.assertTrue(changed2)
        self.assertFalse(switch2)
        self.assertEqual(order2, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
