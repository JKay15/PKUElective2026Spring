#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import unittest

from autoelective.config import AutoElectiveConfig
from autoelective.preflight import run_preflight
from autoelective.utils import Singleton


def _run_preflight_with_ini(text: str):
    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".ini")
    old_env = os.environ.get("AUTOELECTIVE_CONFIG_INI")
    try:
        tmp.write(text)
        tmp.flush()
        tmp.close()

        os.environ["AUTOELECTIVE_CONFIG_INI"] = tmp.name
        Singleton._inst.pop(AutoElectiveConfig, None)
        cfg = AutoElectiveConfig()
        return run_preflight(cfg)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        if old_env is None:
            os.environ.pop("AUTOELECTIVE_CONFIG_INI", None)
        else:
            os.environ["AUTOELECTIVE_CONFIG_INI"] = old_env
        Singleton._inst.pop(AutoElectiveConfig, None)


class PreflightConfigOfflineTest(unittest.TestCase):
    def test_provider_baidu_missing_keys_error(self):
        issues = _run_preflight_with_ini(
            """
[client]
refresh_interval=4
random_deviation=0.01
elective_client_pool_size=2

[captcha]
provider=baidu
baidu_api_key=
baidu_secret_key=
"""
        )
        errs = [i for i in issues if i.level == "ERROR"]
        self.assertTrue(any(i.code == "captcha_key_missing" and i.key_path == "captcha.baidu_api_key" for i in errs))
        self.assertTrue(any(i.code == "captcha_key_missing" and i.key_path == "captcha.baidu_secret_key" for i in errs))

    def test_provider_qwen_missing_dashscope_key_error(self):
        issues = _run_preflight_with_ini(
            """
[client]
refresh_interval=4
random_deviation=0.01
elective_client_pool_size=2

[captcha]
provider=qwen3-vl-flash
dashscope_api_key=
"""
        )
        errs = [i for i in issues if i.level == "ERROR"]
        self.assertTrue(any(i.code == "captcha_key_missing" and i.key_path == "captcha.dashscope_api_key" for i in errs))

    def test_refresh_interval_low_warn(self):
        issues = _run_preflight_with_ini(
            """
[client]
refresh_interval=0.2
random_deviation=0.01
elective_client_pool_size=1

[captcha]
provider=dummy
"""
        )
        errs = [i for i in issues if i.level == "ERROR"]
        warns = [i for i in issues if i.level == "WARN"]
        self.assertEqual(errs, [])
        self.assertTrue(any(i.code == "refresh_interval_low" for i in warns))

    def test_fallback_provider_missing_key_error(self):
        issues = _run_preflight_with_ini(
            """
[client]
refresh_interval=4
random_deviation=0.01
elective_client_pool_size=2

[captcha]
provider=dummy
fallback_providers=gemini
gemini_api_key=
"""
        )
        errs = [i for i in issues if i.level == "ERROR"]
        self.assertTrue(any(i.code == "captcha_fallback_key_missing" and i.key_path == "captcha.gemini_api_key" for i in errs))


if __name__ == "__main__":
    unittest.main()

