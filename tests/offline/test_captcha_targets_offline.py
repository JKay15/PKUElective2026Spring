#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from autoelective.captcha.targets import (
    default_targets_from_config,
    format_target,
    parse_targets_csv,
)


class _Cfg:
    captcha_provider = "openai"
    captcha_fallback_providers = ["gemini", "openai", "baidu"]


class CaptchaTargetsOfflineTest(unittest.TestCase):
    def test_parse_targets_csv_supports_openai_multi_model(self):
        targets = parse_targets_csv("openai:qwen3-vl-flash,openai:qwen3-vl-plus,gemini")
        self.assertEqual(
            targets,
            [
                ("openai", "qwen3-vl-flash"),
                ("openai", "qwen3-vl-plus"),
                ("gemini", None),
            ],
        )

    def test_parse_targets_csv_dedups_by_provider_model_pair(self):
        targets = parse_targets_csv("openai:qwen3-vl-flash,openai:qwen3-vl-flash,gemini,gemini")
        self.assertEqual(
            targets,
            [("openai", "qwen3-vl-flash"), ("gemini", None)],
        )

    def test_non_openai_model_override_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_targets_csv("baidu:abc")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_targets_csv("qwen3-vl-flash")

    def test_default_targets_from_config_uses_provider_list(self):
        targets = default_targets_from_config(_Cfg())
        self.assertEqual(targets, [("openai", None), ("gemini", None), ("baidu", None)])

    def test_format_target(self):
        self.assertEqual(format_target("openai", "qwen3-vl-flash"), "openai:qwen3-vl-flash")
        self.assertEqual(format_target("gemini", None), "gemini")


if __name__ == "__main__":
    unittest.main()
