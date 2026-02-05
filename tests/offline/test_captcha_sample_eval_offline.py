#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from autoelective.captcha.captcha import Captcha


class _DummyRecognizer:
    def __init__(self, code):
        self._code = code

    def recognize(self, raw):
        return Captcha(self._code, None, None, None, None)


class CaptchaSampleEvalOfflineTest(unittest.TestCase):
    def test_eval_script_outputs_metrics(self):
        tmpdir = tempfile.mkdtemp(prefix="captcha_eval_")
        labels_path = os.path.join(tmpdir, "labels.json")
        sample_id = "sample_1"
        img_path = os.path.join(tmpdir, sample_id + ".png")
        meta_path = os.path.join(tmpdir, sample_id + ".json")

        # minimal png header
        with open(img_path, "wb") as fp:
            fp.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00")
        with open(meta_path, "w", encoding="utf-8") as fp:
            json.dump({"label": "ABCD"}, fp, ensure_ascii=False)
        with open(labels_path, "w", encoding="utf-8") as fp:
            json.dump({sample_id: "ABCD"}, fp, ensure_ascii=False)

        try:
            import scripts.captcha_sample_eval as eval_script

            out = io.StringIO()
            dummy = _DummyRecognizer("ABCD")

            with mock.patch.object(eval_script, "get_recognizer", new=lambda _p: dummy), \
                 mock.patch.object(eval_script, "AutoElectiveConfig", new=lambda: None), \
                 mock.patch.object(eval_script, "main", wraps=eval_script.main) as _:
                argv = [
                    "captcha_sample_eval.py",
                    "--sample-dir",
                    tmpdir,
                    "--labels",
                    labels_path,
                    "--providers",
                    "dummy",
                ]
                with mock.patch("sys.argv", new=argv), redirect_stdout(out):
                    rc = eval_script.main()

            text = out.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("== dummy ==", text)
            self.assertIn("exact=1.000", text)
            self.assertIn("latency_ms:", text)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
