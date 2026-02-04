import os
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


if __name__ == "__main__":
    unittest.main()
