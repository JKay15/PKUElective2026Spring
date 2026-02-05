#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace

from autoelective.hook import with_etree, check_elective_title, check_elective_tips
from autoelective.exceptions import (
    InvalidTokenError,
    OperationTimeoutError,
    ElectionFailedError,
    QuotaLimitedError,
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


class HookHtmlVariantsOfflineTest(unittest.TestCase):
    def test_errInfo_more_tolerant_structure(self):
        html = (
            "<html><head><title>系统提示</title></head><body>"
            "<div><table><tr><td><strong>出错提示:</strong>token无效</td></tr></table></div>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(InvalidTokenError):
            check_elective_title(r)

    def test_tips_timeout_variant_no_punctuation(self):
        html = (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'>对不起，超时操作，请重新登录</td>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(OperationTimeoutError):
            check_elective_tips(r)

    def test_tips_failed_variant(self):
        html = (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'><div>选课操作失败，请稍后再试</div></td>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(ElectionFailedError):
            check_elective_tips(r)

    def test_tips_quota_variant(self):
        html = (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'>该课程选课人数已满，请稍后再试。</td>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(QuotaLimitedError):
            check_elective_tips(r)


if __name__ == "__main__":
    unittest.main()

