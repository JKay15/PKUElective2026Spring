import json
import unittest
from unittest import mock

import requests
from requests import Response
from requests.hooks import dispatch_hook

from autoelective.iaaa import IAAAClient
from autoelective.elective import ElectiveClient
from autoelective.parser import get_tables, get_courses, get_courses_with_detail
from autoelective.exceptions import (
    IAAAIncorrectPasswordError,
    ElectionRepeatedError,
    StatusCodeError,
    ServerError,
)


def _make_response(prep, status_code=200, content=b"", headers=None):
    resp = Response()
    resp.status_code = status_code
    resp.url = prep.url
    resp.request = prep
    resp._content = content
    resp.headers = headers or {}
    resp.encoding = "utf-8"
    resp.history = []
    return resp


def _fake_send(self, prep, **kwargs):
    url = prep.url
    if "oauthlogin.do" in url:
        payload = json.dumps(
            {"success": False, "errors": {"code": "E01", "msg": "bad"}}
        ).encode("utf-8")
        resp = _make_response(prep, content=payload, headers={"Content-Type": "application/json"})
    elif "SupplyCancel.do" in url:
        html = (
            "<html><head><title>选课</title></head><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>班号</th><th>开课单位</th><th>限数/已选</th><th>补选</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>课程A</td><td>01</td><td>学院A</td><td>30/10</td>"
            "<td><a href='/supplement/electSupplement.do?course=1'>补选</a></td>"
            "</tr>"
            "</table>"
            "<table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>班号</th><th>开课单位</th>"
            "</tr>"
            "<tr class='datagrid-even'>"
            "<td>课程B</td><td>02</td><td>学院B</td>"
            "</tr>"
            "</table></table>"
            "</body></html>"
        )
        resp = _make_response(prep, content=html.encode("utf-8"))
    elif "ssoLogin.do" in url or "electSupplement.do" in url:
        html = (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'><table><table><td>ignore</td><td>您已经选过该课程了。</td>"
            "</table></table></td>"
            "</body></html>"
        )
        resp = _make_response(prep, content=html.encode("utf-8"))
    else:
        resp = _make_response(prep, content=b"OK")
    return dispatch_hook("response", prep.hooks, resp, **kwargs)


class HttpMockTest(unittest.TestCase):
    @mock.patch("requests.sessions.Session.send", new=_fake_send)
    def test_iaaa_login_incorrect_password(self):
        client = IAAAClient()
        with self.assertRaises(IAAAIncorrectPasswordError):
            client.oauth_login("u", "p")

    def test_iaaa_login_success(self):
        def _send(self, prep, **kwargs):
            payload = json.dumps({"success": True}).encode("utf-8")
            resp = _make_response(prep, content=payload, headers={"Content-Type": "application/json"})
            return dispatch_hook("response", prep.hooks, resp, **kwargs)

        with mock.patch("requests.sessions.Session.send", new=_send):
            client = IAAAClient()
            resp = client.oauth_login("u", "p")
            self.assertEqual(resp.status_code, 200)

    @mock.patch("requests.sessions.Session.send", new=_fake_send)
    def test_elective_tips_repeated(self):
        client = ElectiveClient(id=1)
        with self.assertRaises(ElectionRepeatedError):
            client.get_ElectSupplement("/supplement/electSupplement.do?x=1")

    @mock.patch("requests.sessions.Session.send", new=_fake_send)
    def test_supply_cancel_parse(self):
        client = ElectiveClient(id=1)
        resp = client.get_SupplyCancel("u")
        tables = get_tables(resp._tree)
        self.assertGreaterEqual(len(tables), 2)
        plans = get_courses_with_detail(tables[0])
        elected = get_courses(tables[1])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].name, "课程A")
        self.assertEqual(plans[0].class_no, 1)
        self.assertEqual(plans[0].school, "学院A")
        self.assertEqual(plans[0].max_quota, 30)
        self.assertEqual(plans[0].used_quota, 10)
        self.assertEqual(len(elected), 1)
        self.assertEqual(elected[0].name, "课程B")
        self.assertEqual(elected[0].class_no, 2)
        self.assertEqual(elected[0].school, "学院B")

    def test_status_code_error(self):
        def _send(self, prep, **kwargs):
            resp = _make_response(prep, status_code=404, content=b"not found")
            return dispatch_hook("response", prep.hooks, resp, **kwargs)

        with mock.patch("requests.sessions.Session.send", new=_send):
            client = IAAAClient()
            with self.assertRaises(StatusCodeError):
                client.oauth_login("u", "p")

    def test_server_error(self):
        def _send(self, prep, **kwargs):
            if "validate.do" in prep.url:
                resp = _make_response(prep, status_code=500, content=b"error")
            else:
                resp = _make_response(prep, status_code=200, content=b"ok")
            return dispatch_hook("response", prep.hooks, resp, **kwargs)

        with mock.patch("requests.sessions.Session.send", new=_send):
            client = ElectiveClient(id=1)
            with self.assertRaises(ServerError):
                client.get_Validate("u", "1234")


if __name__ == "__main__":
    unittest.main()
