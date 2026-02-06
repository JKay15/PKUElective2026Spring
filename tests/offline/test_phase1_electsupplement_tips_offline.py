#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import unittest
from types import SimpleNamespace

from autoelective.hook import with_etree, check_elective_tips
from autoelective.exceptions import (
    ElectionFailedError,
    OperationTimeoutError,
    QuotaLimitedError,
    MutexCourseError,
    ElectionSuccess,
)


class FakeResponse(object):
    def __init__(self, text="", status_code=200):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self.url = "https://example.com"
        self.headers = {}
        self.request = SimpleNamespace()
        self.history = []


def _fixture_path(name):
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "fixtures",
        "2026_phase1",
        name,
    )


class Phase1ElectSupplementTipsOfflineTest(unittest.TestCase):
    def _load(self, name):
        path = _fixture_path(name)
        with open(path, "rb") as fp:
            return fp.read().decode("utf-8", errors="ignore")

    def _assert_raises(self, name, exc_type):
        html = self._load(name)
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(exc_type):
            check_elective_tips(r)

    def test_tips_quota(self):
        self._assert_raises("electsupplement_tips_quota.html", QuotaLimitedError)

    def test_tips_failed(self):
        self._assert_raises("electsupplement_tips_failed.html", ElectionFailedError)

    def test_tips_timeout(self):
        self._assert_raises("electsupplement_tips_timeout.html", OperationTimeoutError)

    def test_tips_mutex(self):
        self._assert_raises("electsupplement_tips_mutex.html", MutexCourseError)

    def test_tips_success(self):
        self._assert_raises("electsupplement_tips_success.html", ElectionSuccess)


if __name__ == "__main__":
    unittest.main()
