#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

import autoelective.loop as loop


class HtmlParseRecoveryOfflineTest(unittest.TestCase):
    def test_html_parse_threshold_triggers_reset(self):
        calls = {"n": 0}
        orig = {
            "HTML_PARSE_ERROR_THRESHOLD": loop.HTML_PARSE_ERROR_THRESHOLD,
            "HTML_PARSE_RESET_SESSIONS": loop.HTML_PARSE_RESET_SESSIONS,
            "HTML_PARSE_COOLDOWN_SECONDS": loop.HTML_PARSE_COOLDOWN_SECONDS,
            "_html_parse_streak": loop._html_parse_streak,
            "_reset_client_pool": loop._reset_client_pool,
        }

        def _reset_pool(_reason, force=False):
            calls["n"] += 1
            return True

        try:
            loop.HTML_PARSE_ERROR_THRESHOLD = 2
            loop.HTML_PARSE_RESET_SESSIONS = True
            loop.HTML_PARSE_COOLDOWN_SECONDS = 0
            loop._html_parse_streak = 0
            loop._reset_client_pool = _reset_pool

            loop._record_html_parse_error("unit", count_stat=False)
            self.assertEqual(calls["n"], 0)
            loop._record_html_parse_error("unit", count_stat=False)
            self.assertEqual(calls["n"], 1)
            self.assertEqual(loop._html_parse_streak, 0)
        finally:
            loop.HTML_PARSE_ERROR_THRESHOLD = orig["HTML_PARSE_ERROR_THRESHOLD"]
            loop.HTML_PARSE_RESET_SESSIONS = orig["HTML_PARSE_RESET_SESSIONS"]
            loop.HTML_PARSE_COOLDOWN_SECONDS = orig["HTML_PARSE_COOLDOWN_SECONDS"]
            loop._html_parse_streak = orig["_html_parse_streak"]
            loop._reset_client_pool = orig["_reset_client_pool"]


if __name__ == "__main__":
    unittest.main()
