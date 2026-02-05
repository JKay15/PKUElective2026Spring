#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from autoelective.captcha.adaptive import CaptchaAdaptiveManager


class TestCaptchaAdaptiveOffline(unittest.TestCase):
    def test_no_reorder_with_insufficient_samples(self):
        mgr = CaptchaAdaptiveManager(
            ["a", "b"], enabled=True, min_samples=3, epsilon=0.1, h_init=0.5
        )
        order, switch, changed = mgr.maybe_reorder(["a", "b"])
        self.assertEqual(order, ["a", "b"])
        self.assertFalse(switch)
        self.assertFalse(changed)

    def test_reorder_when_better(self):
        mgr = CaptchaAdaptiveManager(
            ["a", "b"], enabled=True, min_samples=2, epsilon=0.1, h_init=0.5,
            latency_alpha=1.0, h_alpha=1.0
        )
        mgr.record_attempt("a", False, latency=1.0, h_latency=0.5)
        mgr.record_attempt("a", False, latency=1.0, h_latency=0.5)
        mgr.record_attempt("b", True, latency=0.2, h_latency=0.5)
        mgr.record_attempt("b", True, latency=0.2, h_latency=0.5)

        order, switch, changed = mgr.maybe_reorder(["a", "b"])
        self.assertTrue(changed)
        self.assertTrue(switch)
        self.assertEqual(order[0], "b")

    def test_probe_selects_least_samples(self):
        mgr = CaptchaAdaptiveManager(["a", "b", "c"], enabled=True, min_samples=1)
        mgr.record_attempt("a", True, latency=0.5, h_latency=0.2)
        provider = mgr.select_probe_provider(["a", "b", "c"])
        self.assertEqual(provider, "b")


if __name__ == "__main__":
    unittest.main()
