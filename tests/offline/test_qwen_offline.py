import os
import unittest
from unittest import mock
from io import BytesIO
from pathlib import Path

from PIL import Image

from autoelective.captcha import get_recognizer
from autoelective.captcha.captcha import Captcha
from autoelective.config import AutoElectiveConfig
from autoelective.utils import Singleton


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
    def setUp(self):
        self._cfg_old = os.environ.get("AUTOELECTIVE_CONFIG_INI")
        cfg = Path(__file__).resolve().parents[2] / "config.sample.ini"
        os.environ["AUTOELECTIVE_CONFIG_INI"] = str(cfg)
        Singleton._inst.pop(AutoElectiveConfig, None)

    def tearDown(self):
        if self._cfg_old is None:
            os.environ.pop("AUTOELECTIVE_CONFIG_INI", None)
        else:
            os.environ["AUTOELECTIVE_CONFIG_INI"] = self._cfg_old
        Singleton._inst.pop(AutoElectiveConfig, None)

    @mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_qwen_recognizer_parses_json_text(self):
        r = get_recognizer("qwen3-vl-flash")
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")

    @mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_qwen_ocr_recognizer_parses_json_text(self):
        r = get_recognizer("qwen-vl-ocr-2025-11-20")
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")


if __name__ == "__main__":
    unittest.main()
