#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import unittest
from types import SimpleNamespace

from autoelective.hook import with_etree, check_elective_title, check_elective_tips
from autoelective.exceptions import (
    OperationTimeoutError,
    ElectionFailedError,
    QuotaLimitedError,
    CaptchaError,
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


class ElectSupplementTipsFixtureOfflineTest(unittest.TestCase):
    def _load(self, name):
        path = _fixture_path(name)
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read()

    def _assert_tips(self, html, exc_type):
        r = FakeResponse(text=html)
        with_etree(r)
        # Should not raise on title if msgTips exists.
        check_elective_title(r)
        with self.assertRaises(exc_type):
            check_elective_tips(r)

    def test_quota_limit_fixture(self):
        html = self._load("electsupplement_tips_quota.html")
        self._assert_tips(html, QuotaLimitedError)

    def test_timeout_fixture(self):
        html = self._load("electsupplement_tips_timeout.html")
        self._assert_tips(html, OperationTimeoutError)

    def test_div_fixture(self):
        html = self._load("electsupplement_tips_div.html")
        self._assert_tips(html, ElectionFailedError)

    def test_system_prompt_fixture(self):
        html = self._load("electsupplement_system_prompt.html")
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(CaptchaError):
            check_elective_title(r)


if __name__ == "__main__":
    unittest.main()
