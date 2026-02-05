#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest import mock

from autoelective.captcha.adaptive import CaptchaAdaptiveManager
import autoelective.loop as loop


class AdaptivePersistOfflineTest(unittest.TestCase):
    def test_persist_and_load_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "adaptive_snapshot.json")

            mgr = CaptchaAdaptiveManager(["a", "b"], enabled=True, min_samples=1)
            mgr.record_attempt("a", True, latency=0.2, h_latency=0.5)
            mgr.record_attempt("a", False, latency=0.3, h_latency=0.6)
            mgr.record_attempt("b", True, latency=0.1, h_latency=0.4)

            orig = {
                "enable": loop.CAPTCHA_ADAPTIVE_PERSIST_ENABLE,
                "path": loop.CAPTCHA_ADAPTIVE_PERSIST_PATH,
                "interval": loop.CAPTCHA_ADAPTIVE_PERSIST_INTERVAL_SECONDS,
                "loaded": loop._adaptive_snapshot_loaded,
                "last_at": loop._adaptive_persist_last_at,
                "adaptive": loop.adaptive,
            }

            loop.CAPTCHA_ADAPTIVE_PERSIST_ENABLE = True
            loop.CAPTCHA_ADAPTIVE_PERSIST_PATH = path
            loop.CAPTCHA_ADAPTIVE_PERSIST_INTERVAL_SECONDS = 0.0
            loop._adaptive_persist_last_at = 0.0

            try:
                with mock.patch.object(loop, "adaptive", new=mgr):
                    ok = loop._maybe_persist_adaptive(force=True)
                    self.assertTrue(ok)
                    self.assertTrue(os.path.exists(path))

                mgr2 = CaptchaAdaptiveManager(["a", "b"], enabled=True, min_samples=1)
                loop._adaptive_snapshot_loaded = False
                with mock.patch.object(loop, "adaptive", new=mgr2):
                    ok = loop._load_adaptive_snapshot_once()
                    self.assertTrue(ok)

                snap = mgr2.snapshot()
                self.assertEqual(snap["stats"]["a"]["count"], 2)
                self.assertEqual(snap["stats"]["a"]["success"], 1)
                self.assertEqual(snap["stats"]["a"]["failure"], 1)
                self.assertEqual(snap["stats"]["b"]["count"], 1)
                self.assertEqual(snap["stats"]["b"]["success"], 1)
            finally:
                loop.CAPTCHA_ADAPTIVE_PERSIST_ENABLE = orig["enable"]
                loop.CAPTCHA_ADAPTIVE_PERSIST_PATH = orig["path"]
                loop.CAPTCHA_ADAPTIVE_PERSIST_INTERVAL_SECONDS = orig["interval"]
                loop._adaptive_snapshot_loaded = orig["loaded"]
                loop._adaptive_persist_last_at = orig["last_at"]


if __name__ == "__main__":
    unittest.main()

