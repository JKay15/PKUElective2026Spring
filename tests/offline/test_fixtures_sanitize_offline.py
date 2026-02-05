#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from autoelective.fixtures import redact_url, sanitize_bytes, sanitize_text


class FixturesSanitizeOfflineTest(unittest.TestCase):
    def test_sanitize_text_redacts_student_id_and_tokens(self):
        student_id = "2400012345"
        s = (
            "xh=2400012345 token=abc123 sida=0123456789abcdef0123456789abcdef "
            "JSESSIONID=foo; PHPSESSID=bar"
        )
        out = sanitize_text(s, student_id=student_id)
        self.assertNotIn(student_id, out)
        self.assertIn("STUDENT_ID", out)
        self.assertIn("token=TOKEN", out)
        self.assertIn("sida=SIDA", out)
        self.assertIn("JSESSIONID=JSESSIONID", out)
        self.assertIn("PHPSESSID=PHPSESSID", out)

    def test_redact_url_query_params(self):
        url = (
            "https://example.com/path?"
            "xh=2400012345&token=abc&sida=0123456789abcdef0123456789abcdef&ok=1"
        )
        out = redact_url(url, student_id="2400012345")
        self.assertIn("xh=REDACTED", out)
        self.assertIn("token=REDACTED", out)
        self.assertIn("sida=REDACTED", out)
        self.assertIn("ok=1", out)

    def test_sanitize_bytes_leaves_binary_unchanged(self):
        raw = b"\xff\xd8\xff\x00\x01\x02"  # jpeg-ish
        out = sanitize_bytes(raw, content_type="image/jpeg", student_id="2400012345")
        self.assertEqual(raw, out)

    def test_sanitize_bytes_redacts_html(self):
        raw = b"<html><body>xh=2400012345 token=abc</body></html>"
        out = sanitize_bytes(raw, content_type="text/html", student_id="2400012345")
        self.assertIn(b"STUDENT_ID", out)
        self.assertIn(b"token=TOKEN", out)


if __name__ == "__main__":
    unittest.main()

