#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

import autoelective.loop as loop


class RefreshJitterOfflineTest(unittest.TestCase):
    def test_no_deviation_is_deterministic_and_respects_min(self):
        orig = {
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
        }
        try:
            loop.MIN_REFRESH_INTERVAL = 5.0
            loop.refresh_random_deviation = 0.0

            loop.refresh_interval = 1.0
            self.assertEqual(loop._get_refresh_interval(), 5.0)

            loop.refresh_interval = 10.0
            self.assertEqual(loop._get_refresh_interval(), 10.0)
        finally:
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]

    def test_jitter_bounds_and_varies(self):
        orig = {
            "MIN_REFRESH_INTERVAL": loop.MIN_REFRESH_INTERVAL,
            "refresh_interval": loop.refresh_interval,
            "refresh_random_deviation": loop.refresh_random_deviation,
            "rand": loop.random.random,
        }
        try:
            loop.MIN_REFRESH_INTERVAL = 0.1
            loop.refresh_interval = 10.0
            loop.refresh_random_deviation = 0.2

            seq = iter([0.0, 1.0, 0.5, 0.25, 0.75])
            with mock.patch.object(loop.random, "random", new=lambda: next(seq)):
                vals = [loop._get_refresh_interval() for _ in range(5)]

            # exact values for the chosen sequence
            self.assertEqual(vals[0], 8.0)   # -dev
            self.assertEqual(vals[1], 12.0)  # +dev
            self.assertEqual(vals[2], 10.0)  # center
            self.assertEqual(vals[3], 9.0)
            self.assertEqual(vals[4], 11.0)

            low = loop.refresh_interval * (1.0 - loop.refresh_random_deviation)
            high = loop.refresh_interval * (1.0 + loop.refresh_random_deviation)
            self.assertTrue(all(low <= v <= high for v in vals))
            self.assertGreater(len(set(vals)), 1)
        finally:
            loop.MIN_REFRESH_INTERVAL = orig["MIN_REFRESH_INTERVAL"]
            loop.refresh_interval = orig["refresh_interval"]
            loop.refresh_random_deviation = orig["refresh_random_deviation"]
            loop.random.random = orig["rand"]


if __name__ == "__main__":
    unittest.main()

