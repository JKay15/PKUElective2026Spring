import unittest
from types import SimpleNamespace

from autoelective.hook import (
    with_etree,
    check_status_code,
    check_iaaa_success,
    check_elective_title,
    check_elective_tips,
)
from autoelective.exceptions import (
    ServerError,
    IAAAIncorrectPasswordError,
    IAAAForbiddenError,
    IAAANotSuccessError,
    InvalidTokenError,
    ElectionRepeatedError,
)


class FakeResponse(object):
    def __init__(self, text="", status_code=200, json_data=None, url="https://example.com"):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self._json_data = json_data
        self.url = url
        self.headers = {}
        self.request = SimpleNamespace()
        self.history = []

    def json(self):
        return self._json_data


class HookOfflineTest(unittest.TestCase):
    def test_status_code_server_error(self):
        r = FakeResponse(status_code=500)
        with self.assertRaises(ServerError):
            check_status_code(r)

    def test_iaaa_success(self):
        r = FakeResponse(json_data={"success": True})
        check_iaaa_success(r)

    def test_iaaa_incorrect_password(self):
        r = FakeResponse(json_data={"success": False, "errors": {"code": "E01", "msg": "bad"}})
        with self.assertRaises(IAAAIncorrectPasswordError):
            check_iaaa_success(r)

    def test_iaaa_forbidden(self):
        r = FakeResponse(json_data={"success": False, "errors": {"code": "E21", "msg": "forbidden"}})
        with self.assertRaises(IAAAForbiddenError):
            check_iaaa_success(r)

    def test_iaaa_not_success(self):
        r = FakeResponse(json_data={"success": False})
        with self.assertRaises(IAAANotSuccessError):
            check_iaaa_success(r)

    def test_elective_invalid_token(self):
        html = (
            "<html><head><title>系统提示</title></head><body>"
            "<table><table><table><td><strong>出错提示:</strong>token无效</td></table></table></table>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(InvalidTokenError):
            check_elective_title(r)

    def test_elective_tips_repeated(self):
        html = (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'><table><table><td>ignore</td><td>您已经选过该课程了。</td>"
            "</table></table></td>"
            "</body></html>"
        )
        r = FakeResponse(text=html)
        with_etree(r)
        with self.assertRaises(ElectionRepeatedError):
            check_elective_tips(r)


if __name__ == "__main__":
    unittest.main()
