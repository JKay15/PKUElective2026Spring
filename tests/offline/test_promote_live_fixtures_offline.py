#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import shutil
import tempfile
import unittest


class PromoteLiveFixturesOfflineTest(unittest.TestCase):
    def test_promote_picks_latest_by_ts(self):
        tmp = tempfile.mkdtemp(prefix="promote_fixtures_")
        src = os.path.join(tmp, "src")
        dst = os.path.join(tmp, "dst")
        os.makedirs(src, exist_ok=True)

        # Older capture
        with open(os.path.join(src, "001_helpcontroller_20260101T000000Z.html"), "wb") as fp:
            fp.write(b"<html>old</html>")
        with open(os.path.join(src, "001_helpcontroller_20260101T000000Z.meta.json"), "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "name": "helpcontroller",
                    "ts": "20260101T000000Z",
                    "path": "001_helpcontroller_20260101T000000Z.html",
                },
                fp,
                ensure_ascii=False,
            )

        # Newer capture
        with open(os.path.join(src, "002_helpcontroller_20260102T000000Z.html"), "wb") as fp:
            fp.write(b"<html>new</html>")
        with open(os.path.join(src, "002_helpcontroller_20260102T000000Z.meta.json"), "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "name": "helpcontroller",
                    "ts": "20260102T000000Z",
                    "path": "002_helpcontroller_20260102T000000Z.html",
                },
                fp,
                ensure_ascii=False,
            )

        try:
            from scripts.promote_live_fixtures import main

            rc = main(["--src", src, "--dst", dst, "--names", "helpcontroller", "--strict"])
            self.assertEqual(rc, 0)

            out_html = os.path.join(dst, "helpcontroller.html")
            out_meta = os.path.join(dst, "helpcontroller.meta.json")
            out_manifest = os.path.join(dst, "MANIFEST.json")
            self.assertTrue(os.path.isfile(out_html))
            self.assertTrue(os.path.isfile(out_meta))
            self.assertTrue(os.path.isfile(out_manifest))

            with open(out_html, "rb") as fp:
                body = fp.read()
            self.assertIn(b"new", body)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

