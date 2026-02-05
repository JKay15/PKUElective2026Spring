#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest import mock

import autoelective.loop as loop


class NotInOperationBackoffOfflineTest(unittest.TestCase):
    def _run_case(self, delta_s, expected_mr, expected_cooldown):
        now = 1_000_000_000.0
        schedule = [
            {
                "name": "补退选第一阶段候补选课",
                "start_ts": now + float(delta_s),
                "end_ts": now + float(delta_s) + 3600.0,
            }
        ]

        calls = {"cooldown": None}

        def _enter_cd(_reason, seconds):
            calls["cooldown"] = float(seconds)

        orig = {
            "NOT_IN_OPERATION_DYNAMIC_ENABLE": loop.NOT_IN_OPERATION_DYNAMIC_ENABLE,
            "NOT_IN_OPERATION_MIN_REFRESH": loop.NOT_IN_OPERATION_MIN_REFRESH,
            "NOT_IN_OPERATION_COOLDOWN_SECONDS": loop.NOT_IN_OPERATION_COOLDOWN_SECONDS,
            "NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX": loop.NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX,
            "_get_help_schedule": loop._get_help_schedule,
            "_enter_cooldown": loop._enter_cooldown,
            "_not_in_operation_min_refresh_dynamic": loop._not_in_operation_min_refresh_dynamic,
            "_not_in_operation_backoff_reason": loop._not_in_operation_backoff_reason,
        }

        try:
            loop.NOT_IN_OPERATION_DYNAMIC_ENABLE = True
            loop.NOT_IN_OPERATION_MIN_REFRESH = 5.0
            loop.NOT_IN_OPERATION_COOLDOWN_SECONDS = 30.0
            loop.NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX = 3600.0
            loop._not_in_operation_min_refresh_dynamic = loop.NOT_IN_OPERATION_MIN_REFRESH
            loop._not_in_operation_backoff_reason = ""

            with mock.patch.object(loop.time, "time", new=lambda: now), \
                 mock.patch.object(loop, "_get_help_schedule", new=lambda elective=None, force_refresh=False: schedule), \
                 mock.patch.object(loop, "_enter_cooldown", new=_enter_cd):
                mr, reason = loop._update_not_in_operation_backoff(elective=None)

            self.assertEqual(mr, expected_mr)
            self.assertIsNotNone(calls["cooldown"])
            self.assertEqual(int(calls["cooldown"]), int(expected_cooldown))
            self.assertIn("next=", reason)
        finally:
            loop.NOT_IN_OPERATION_DYNAMIC_ENABLE = orig["NOT_IN_OPERATION_DYNAMIC_ENABLE"]
            loop.NOT_IN_OPERATION_MIN_REFRESH = orig["NOT_IN_OPERATION_MIN_REFRESH"]
            loop.NOT_IN_OPERATION_COOLDOWN_SECONDS = orig["NOT_IN_OPERATION_COOLDOWN_SECONDS"]
            loop.NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX = orig[
                "NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX"
            ]
            loop._get_help_schedule = orig["_get_help_schedule"]
            loop._enter_cooldown = orig["_enter_cooldown"]
            loop._not_in_operation_min_refresh_dynamic = orig["_not_in_operation_min_refresh_dynamic"]
            loop._not_in_operation_backoff_reason = orig["_not_in_operation_backoff_reason"]

    def test_piecewise_policy(self):
        # (delta -> expected min_refresh, expected cooldown)
        cases = [
            (48 * 3600, 1800, 30),
            (8 * 3600, 600, 30),
            (3 * 3600, 120, 30),
            (45 * 60, 30, 30),
            (10 * 60, 10, 10),
            (60, 5, 5),
        ]
        for delta, mr, cd in cases:
            with self.subTest(delta=delta):
                self._run_case(delta, mr, cd)


if __name__ == "__main__":
    unittest.main()

