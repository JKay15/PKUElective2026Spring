import os
import tempfile
import unittest
from unittest import mock
from io import BytesIO

from autoelective.captcha.gemini import GeminiVLMRecognizer
from autoelective.captcha.captcha import Captcha
from PIL import Image


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


def _fake_post_ok(self, url, **kwargs):
    return _Resp(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "{\"text\": \"Ab12\"}"},
                        ]
                    }
                }
            ]
        },
    )


class GeminiOfflineTest(unittest.TestCase):
    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_gemini_recognizer_parses_json_text(self):
        r = GeminiVLMRecognizer()
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")

    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"}, clear=False)
    def test_gemini_recognizer_appends_local_prompt(self):
        sent_payloads = []

        def _fake_post_capture(self, url, **kwargs):
            sent_payloads.append(kwargs.get("json") or {})
            return _Resp(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "{\"text\": \"Ab12\"}"},
                                ]
                            }
                        }
                    ]
                },
            )

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fp:
            fp.write("my gemini local prompt")
            prompt_path = fp.name
        old_prompt_file = os.environ.get("AUTOELECTIVE_VLM_PROMPT_FILE")
        try:
            os.environ["AUTOELECTIVE_VLM_PROMPT_FILE"] = prompt_path
            with mock.patch("requests.sessions.Session.post", new=_fake_post_capture):
                r = GeminiVLMRecognizer()
                buf = BytesIO()
                Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
                cap = r.recognize(buf.getvalue())
                self.assertEqual(cap.code, "AB12")
        finally:
            if old_prompt_file is None:
                os.environ.pop("AUTOELECTIVE_VLM_PROMPT_FILE", None)
            else:
                os.environ["AUTOELECTIVE_VLM_PROMPT_FILE"] = old_prompt_file
            if os.path.exists(prompt_path):
                os.unlink(prompt_path)

        self.assertTrue(sent_payloads)
        parts = sent_payloads[-1]["contents"][0]["parts"]
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        self.assertTrue(any("my gemini local prompt" in t for t in text_parts))


if __name__ == "__main__":
    unittest.main()
