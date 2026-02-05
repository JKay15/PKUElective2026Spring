#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

from autoelective import rate_limit


class _FakeTime:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


class _DummyConfig:
    rate_limit_enable = True
    rate_limit_global_rps = 0.0
    rate_limit_global_burst = 0.0
    rate_limit_elective_rps = 2.0
    rate_limit_elective_burst = 2.0
    rate_limit_iaaa_rps = 0.0
    rate_limit_iaaa_burst = 0.0


class RateLimitOfflineTest(unittest.TestCase):
    def test_token_bucket_waits(self):
        fake = _FakeTime()
        with mock.patch.object(rate_limit.time, "monotonic", new=fake.monotonic), \
             mock.patch.object(rate_limit.time, "sleep", new=fake.sleep):
            tb = rate_limit.TokenBucket(rate=2.0, burst=2.0)
            tb.consume()
            tb.consume()
            self.assertEqual(len(fake.slept), 0)
            tb.consume()
            self.assertEqual(len(fake.slept), 1)
            self.assertAlmostEqual(fake.slept[-1], 0.5, places=3)

    def test_rate_limit_throttle(self):
        fake = _FakeTime()
        with mock.patch.object(rate_limit.time, "monotonic", new=fake.monotonic), \
             mock.patch.object(rate_limit.time, "sleep", new=fake.sleep):
            rate_limit.configure(_DummyConfig())
            # first two calls within burst, third should sleep
            rate_limit.throttle("https://elective.pku.edu.cn/elective2008/")
            rate_limit.throttle("https://elective.pku.edu.cn/elective2008/")
            self.assertEqual(len(fake.slept), 0)
            rate_limit.throttle("https://elective.pku.edu.cn/elective2008/")
            self.assertEqual(len(fake.slept), 1)
            self.assertAlmostEqual(fake.slept[-1], 0.5, places=3)


if __name__ == "__main__":
    unittest.main()
