#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
import unittest

import autoelective.loop as loop


class CaptchaSamplingOfflineTest(unittest.TestCase):
    def test_sample_saved_when_enabled(self):
        tmpdir = tempfile.mkdtemp(prefix="captcha_samples_")
        orig = {
            "CAPTCHA_SAMPLE_ENABLE": loop.CAPTCHA_SAMPLE_ENABLE,
            "CAPTCHA_SAMPLE_RATE": loop.CAPTCHA_SAMPLE_RATE,
            "CAPTCHA_SAMPLE_DIR": loop.CAPTCHA_SAMPLE_DIR,
            "_sample_dir_ready": loop._sample_dir_ready,
            "_sample_seq": loop._sample_seq,
        }
        try:
            loop.CAPTCHA_SAMPLE_ENABLE = True
            loop.CAPTCHA_SAMPLE_RATE = 1.0
            loop.CAPTCHA_SAMPLE_DIR = tmpdir
            loop._sample_dir_ready = False
            loop._sample_seq = 0

            loop._maybe_sample_captcha(b"fakeimagebytes", provider="unit", context="test", draw_dt=0.1)

            files = os.listdir(tmpdir)
            self.assertTrue(any(name.endswith(".json") for name in files))
            self.assertTrue(any(name.endswith(".bin") for name in files))
        finally:
            loop.CAPTCHA_SAMPLE_ENABLE = orig["CAPTCHA_SAMPLE_ENABLE"]
            loop.CAPTCHA_SAMPLE_RATE = orig["CAPTCHA_SAMPLE_RATE"]
            loop.CAPTCHA_SAMPLE_DIR = orig["CAPTCHA_SAMPLE_DIR"]
            loop._sample_dir_ready = orig["_sample_dir_ready"]
            loop._sample_seq = orig["_sample_seq"]
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
