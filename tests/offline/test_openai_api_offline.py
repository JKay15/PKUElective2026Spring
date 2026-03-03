import os
import tempfile
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


class OpenAIApiOfflineTest(unittest.TestCase):
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

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_openai_recognizer_parses_json_text(self):
        r = get_recognizer("openai", model_name="qwen3-vl-flash")
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False)
    @mock.patch("requests.sessions.Session.post", new=_fake_post_ok)
    def test_openai_recognizer_accepts_another_model(self):
        r = get_recognizer("openai", model_name="qwen-vl-ocr-2025-11-20")
        buf = BytesIO()
        Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
        cap = r.recognize(buf.getvalue())
        self.assertIsInstance(cap, Captcha)
        self.assertEqual(cap.code, "AB12")

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False)
    def test_vlm_model_attaches_prompt(self):
        sent_payloads = []

        def _fake_post_capture(self, url, **kwargs):
            sent_payloads.append(kwargs.get("json") or {})
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

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fp:
            fp.write("my custom vlm prompt")
            prompt_path = fp.name
        old_prompt_file = os.environ.get("AUTOELECTIVE_VLM_PROMPT_FILE")
        try:
            os.environ["AUTOELECTIVE_VLM_PROMPT_FILE"] = prompt_path
            with mock.patch("requests.sessions.Session.post", new=_fake_post_capture):
                r = get_recognizer("openai", model_name="Qwen/Qwen3-VL-30B-A3B-Instruct")
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
        content = sent_payloads[-1]["messages"][0]["content"]
        text_parts = [p for p in content if p.get("type") == "text"]
        self.assertEqual(len(text_parts), 1)
        self.assertEqual(text_parts[0].get("text"), "my custom vlm prompt")

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False)
    def test_ocr_model_does_not_attach_prompt(self):
        sent_payloads = []

        def _fake_post_capture(self, url, **kwargs):
            sent_payloads.append(kwargs.get("json") or {})
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

        with mock.patch("requests.sessions.Session.post", new=_fake_post_capture):
            r = get_recognizer("openai", model_name="qwen-vl-ocr-latest")
            buf = BytesIO()
            Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
            cap = r.recognize(buf.getvalue())
            self.assertEqual(cap.code, "AB12")

        self.assertTrue(sent_payloads)
        content = sent_payloads[-1]["messages"][0]["content"]
        text_parts = [p for p in content if p.get("type") == "text"]
        self.assertEqual(text_parts, [])

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False)
    def test_vlm_model_without_local_prompt_does_not_attach_prompt(self):
        sent_payloads = []

        def _fake_post_capture(self, url, **kwargs):
            sent_payloads.append(kwargs.get("json") or {})
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

        old_prompt_file = os.environ.get("AUTOELECTIVE_VLM_PROMPT_FILE")
        try:
            os.environ["AUTOELECTIVE_VLM_PROMPT_FILE"] = "/tmp/not-exists-vlm-prompt.txt"
            with mock.patch("requests.sessions.Session.post", new=_fake_post_capture):
                r = get_recognizer("openai", model_name="Qwen/Qwen3-VL-30B-A3B-Instruct")
                buf = BytesIO()
                Image.new("RGB", (16, 16), (255, 255, 255)).save(buf, format="JPEG")
                cap = r.recognize(buf.getvalue())
                self.assertEqual(cap.code, "AB12")
        finally:
            if old_prompt_file is None:
                os.environ.pop("AUTOELECTIVE_VLM_PROMPT_FILE", None)
            else:
                os.environ["AUTOELECTIVE_VLM_PROMPT_FILE"] = old_prompt_file

        self.assertTrue(sent_payloads)
        content = sent_payloads[-1]["messages"][0]["content"]
        text_parts = [p for p in content if p.get("type") == "text"]
        self.assertEqual(text_parts, [])


if __name__ == "__main__":
    unittest.main()
