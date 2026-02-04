import unittest

from autoelective.captcha import get_recognizer
from autoelective.captcha.captcha import Captcha
from autoelective.exceptions import RecognizerError


class RegistryOfflineTest(unittest.TestCase):
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
