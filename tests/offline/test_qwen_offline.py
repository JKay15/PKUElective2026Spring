import os
import unittest
from unittest import mock
from io import BytesIO

from PIL import Image

from autoelective.captcha.qwen import Qwen3VlFlashRecognizer, QwenVlOcr20251120Recognizer
from autoelective.captcha.captcha import Captcha


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.headers = {}

    def json(self):
        return self._data


def _fake_post_ok(self, url, **kwargs):
    return _Resp(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": "{\"text\": \"Ab12\"}",
                    }
                }
            ]
        },
    )


class QwenOfflineTest(unittest.TestCase):
    @mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_qwen_recognizer_parses_json_text(self):
        r = Qwen3VlFlashRecognizer()
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")

    @mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_qwen_ocr_recognizer_parses_json_text(self):
        r = QwenVlOcr20251120Recognizer()
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")


if __name__ == "__main__":
    unittest.main()
