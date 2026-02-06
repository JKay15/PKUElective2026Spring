#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(path):
    with open(path, "r", encoding="utf-8") as fp:
        return fp.read()


class DebugDumpSafetyOfflineTest(unittest.TestCase):
    def test_debug_dump_disabled_in_sample_config(self):
        cfg = _read(os.path.join(REPO_ROOT, "config.sample.ini"))
        self.assertIn("debug_dump_request=false", cfg.replace(" ", "").lower())
        self.assertIn("debug_print_request=false", cfg.replace(" ", "").lower())

    def test_debug_dump_paths_are_gitignored(self):
        gitignore = _read(os.path.join(REPO_ROOT, ".gitignore"))
        # Entire log/ is ignored, so request dumps must not end up tracked.
        self.assertIn("log/", gitignore)

    def test_hook_dump_uses_request_log_dir(self):
        hook_py = _read(os.path.join(REPO_ROOT, "autoelective", "hook.py"))
        const_py = _read(os.path.join(REPO_ROOT, "autoelective", "const.py"))
        self.assertIn("REQUEST_LOG_DIR", hook_py)
        self.assertIn("_USER_REQUEST_LOG_DIR", hook_py)
        self.assertIn("REQUEST_LOG_DIR = get_abs_path(\"../log/request/\")", const_py)
        # Ensure dump builds the output path under _USER_REQUEST_LOG_DIR.
        self.assertIn("os.path.join(_USER_REQUEST_LOG_DIR, filename)", hook_py)


if __name__ == "__main__":
    unittest.main()

