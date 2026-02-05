#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective.captcha.adaptive import CaptchaAdaptiveManager
import autoelective.loop as loop


class AdaptiveReportReasonOfflineTest(unittest.TestCase):
    def test_report_includes_reason(self):
        orig = {
            "adaptive": loop.adaptive,
        }

        mgr = CaptchaAdaptiveManager(
            ["a", "b"],
            enabled=True,
            min_samples=1,
            epsilon=0.1,
            update_interval=0,
            fail_streak_degrade=0,
            score_alpha=0.4,
            score_beta=0.6,
        )
        mgr.record_attempt("a", True, latency=0.5, h_latency=0.2)
        mgr.record_attempt("b", True, latency=0.1, h_latency=0.1)

        lines = []

        def _collect(msg, *args, **kwargs):
            lines.append(str(msg))

        try:
            loop.adaptive = mgr
            with mock.patch.object(loop.cout, "info", new=_collect):
                loop._report_adaptive_state()
            joined = "\n".join(lines)
            self.assertIn("Adaptive recommend:", joined)
            self.assertIn("Adaptive reason:", joined)
        finally:
            loop.adaptive = orig["adaptive"]


if __name__ == "__main__":
    unittest.main()
