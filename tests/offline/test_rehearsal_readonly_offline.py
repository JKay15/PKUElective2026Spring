#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from requests.exceptions import RequestException

from autoelective.exceptions import NotInOperationTimeError, ServerError, StatusCodeError
from autoelective.rehearsal import classify_rehearsal_error, extract_operation_window


def _is_failure(strict: bool, strict_only: bool) -> bool:
    if strict_only:
        return bool(strict)
    return True


class RehearsalReadonlyOfflineTest(unittest.TestCase):
    def test_not_in_operation_is_strict_only(self):
        e = NotInOperationTimeError(
            msg="目前不是补退选阶段，因此不能进行相应操作。补退选阶段时间: 2026-02-27 15:00:00 至 2026-03-10 10:00:00"
        )
        kind, strict_only = classify_rehearsal_error(e)
        self.assertEqual(kind, "not_in_operation")
        self.assertTrue(strict_only)
        self.assertFalse(_is_failure(strict=False, strict_only=strict_only))
        self.assertTrue(_is_failure(strict=True, strict_only=strict_only))

        window = extract_operation_window(e)
        self.assertEqual(window, "2026-02-27 15:00:00 -> 2026-03-10 10:00:00")

    def test_other_errors_are_always_failure(self):
        for exc in (
            StatusCodeError(msg="bad status"),
            ServerError(msg="server error"),
            RequestException("network"),
        ):
            kind, strict_only = classify_rehearsal_error(exc)
            self.assertNotEqual(kind, "not_in_operation")
            self.assertFalse(strict_only)
            self.assertTrue(_is_failure(strict=False, strict_only=strict_only))
            self.assertTrue(_is_failure(strict=True, strict_only=strict_only))


if __name__ == "__main__":
    unittest.main()

