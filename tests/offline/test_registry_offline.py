import os
import unittest
from pathlib import Path

from autoelective.captcha import get_recognizer
from autoelective.captcha.captcha import Captcha
from autoelective.config import AutoElectiveConfig
from autoelective.exceptions import RecognizerError
from autoelective.utils import Singleton


class RegistryOfflineTest(unittest.TestCase):
    def setUp(self):
        self._cfg_old = os.environ.get("AUTOELECTIVE_CONFIG_INI")
        self._openai_old = os.environ.get("OPENAI_API_KEY")
        self._dashscope_old = os.environ.get("DASHSCOPE_API_KEY")
        cfg = Path(__file__).resolve().parents[2] / "config.sample.ini"
        os.environ["AUTOELECTIVE_CONFIG_INI"] = str(cfg)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)
        Singleton._inst.pop(AutoElectiveConfig, None)

    def tearDown(self):
        if self._cfg_old is None:
            os.environ.pop("AUTOELECTIVE_CONFIG_INI", None)
        else:
            os.environ["AUTOELECTIVE_CONFIG_INI"] = self._cfg_old
        if self._openai_old is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self._openai_old
        if self._dashscope_old is None:
            os.environ.pop("DASHSCOPE_API_KEY", None)
        else:
            os.environ["DASHSCOPE_API_KEY"] = self._dashscope_old
        Singleton._inst.pop(AutoElectiveConfig, None)

    def test_dummy_recognizer(self):
        recognizer = get_recognizer("dummy")
        result = recognizer.recognize(b"fake")
        self.assertIsInstance(result, Captcha)
        self.assertEqual(result.code, "0000")

    def test_unknown_recognizer(self):
        with self.assertRaises(RecognizerError):
            get_recognizer("unknown")


if __name__ == "__main__":
    unittest.main()
