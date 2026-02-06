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
    InvalidTokenError,
    SessionExpiredError,
    NotInOperationTimeError,
    SharedSessionError,
    SystemException,
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

    def _assert_exc(self, name, exc_type):
        html = self._load(name)
        r = FakeResponse(text=html)
        with_etree(r)
        try:
            check_elective_title(r)
        except exc_type:
            return
        with self.assertRaises(exc_type):
            check_elective_tips(r)

    def test_quota_limit_fixture(self):
        self._assert_exc("electsupplement_tips_quota.html", QuotaLimitedError)

    def test_timeout_fixture(self):
        self._assert_exc("electsupplement_tips_timeout.html", OperationTimeoutError)

    def test_div_fixture(self):
        self._assert_exc("electsupplement_tips_div.html", ElectionFailedError)

    def test_system_prompt_fixture(self):
        self._assert_exc("electsupplement_system_prompt.html", CaptchaError)

    def test_system_prompt_msgtips_not_in_operation(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_not_in_operation.html", NotInOperationTimeError)

    def test_system_prompt_msgtips_token_invalid(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_token_invalid.html", InvalidTokenError)

    def test_system_prompt_msgtips_session_expired(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_session_expired.html", SessionExpiredError)

    def test_system_prompt_msgtips_shared_session(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_shared_session.html", SharedSessionError)

    def test_system_prompt_msgtips_quota(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_quota.html", QuotaLimitedError)

    def test_system_prompt_msgtips_unknown_fail_fast(self):
        self._assert_exc("electsupplement_system_prompt_msgtips_unknown.html", SystemException)


if __name__ == "__main__":
    unittest.main()
