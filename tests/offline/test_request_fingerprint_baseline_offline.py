#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import unittest
from unittest import mock

import requests
from requests import Response
from requests.hooks import dispatch_hook

from autoelective.iaaa import IAAAClient
from autoelective.elective import ElectiveClient
from autoelective.const import ElectiveURL


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


class RequestFingerprintBaselineOfflineTest(unittest.TestCase):
    def test_fingerprint_headers_referer_cookie_and_ua(self):
        captured = []

        def _fake_send(self, prep, **kwargs):
            captured.append(
                {
                    "method": prep.method,
                    "url": prep.url,
                    "headers": dict(prep.headers),
                }
            )

            url = prep.url
            if "oauthlogin.do" in url:
                payload = b'{"success": true, "token": "T"}'
                resp = _make_response(
                    prep,
                    content=payload,
                    headers={"Content-Type": "application/json"},
                )
            elif "DrawServlet" in url:
                png = b"\x89PNG\r\n\x1a\n" + b"FAKE"
                resp = _make_response(prep, content=png, headers={"Content-Type": "image/png"})
            elif "validate.do" in url:
                payload = b'{"valid": "2"}'
                resp = _make_response(
                    prep,
                    content=payload,
                    headers={"Content-Type": "application/json"},
                )
            else:
                html = b"<html><head><title>\xe9\x80\x89\xe8\xaf\xbe</title></head><body>ok</body></html>"
                resp = _make_response(prep, content=html, headers={"Content-Type": "text/html"})

            return dispatch_hook("response", prep.hooks, resp, **kwargs)

        baseline_iaaa_header_keys = {
            "Accept",
            "Accept-Encoding",
            "Accept-Language",
            "Host",
            "Origin",
            "Connection",
        }
        baseline_elective_header_keys = {
            "Accept",
            "Accept-Encoding",
            "Accept-Language",
            "Host",
            "Upgrade-Insecure-Requests",
            "Connection",
        }

        with mock.patch("requests.sessions.Session.send", new=_fake_send), \
             mock.patch("autoelective.rate_limit.throttle", new=lambda _url: 0.0):

            iaaa = IAAAClient()
            iaaa.set_user_agent("UA_IAAA")
            _ = iaaa.oauth_home()
            _ = iaaa.oauth_login("u", "p")

            elect = ElectiveClient(id=1)
            elect.set_user_agent("UA_ELECT")
            # SSO login must include dummy JSESSIONID cookie to avoid 101.
            _ = elect.sso_login("T")

            # Referer strategy must match baseline: SupplyCancel referer=HelpController,
            # while action endpoints referer=SupplyCancel.
            _ = elect.get_SupplyCancel("2400012345")
            _ = elect.get_DrawServlet()
            _ = elect.get_Validate("2400012345", "ABCD")
            _ = elect.get_ElectSupplement("/supplement/electSupplement.do?x=1")

        # default_headers superset check
        self.assertTrue(baseline_iaaa_header_keys.issubset(set(IAAAClient.default_headers)))
        self.assertTrue(baseline_elective_header_keys.issubset(set(ElectiveClient.default_headers)))

        # Find captured requests by endpoint
        def _find_prefix(prefix: str):
            return [r for r in captured if r["url"].startswith(prefix)]

        def _find_contains(contains: str):
            return [r for r in captured if contains in r["url"]]

        # IAAA oauth.jsp has redirectUrl=.../ssoLogin.do inside query params.
        # Match the actual Elective endpoint by URL prefix.
        sso = _find_prefix(ElectiveURL.SSOLogin)
        self.assertTrue(sso, "missing ssoLogin.do request capture")
        cookie = (sso[0]["headers"].get("Cookie") or "")
        self.assertRegex(cookie, r"JSESSIONID=[0-9A-Za-z]{52}!\d+")
        self.assertEqual(sso[0]["headers"].get("User-Agent"), "UA_ELECT")

        supply = _find_prefix(ElectiveURL.SupplyCancel)
        self.assertTrue(supply, "missing SupplyCancel.do capture")
        self.assertEqual(supply[0]["headers"].get("Referer"), ElectiveURL.HelpController)
        self.assertEqual(supply[0]["headers"].get("User-Agent"), "UA_ELECT")

        draw = _find_prefix(ElectiveURL.DrawServlet)
        self.assertTrue(draw, "missing DrawServlet capture")
        self.assertEqual(draw[0]["headers"].get("Referer"), ElectiveURL.SupplyCancel)
        self.assertEqual(draw[0]["headers"].get("User-Agent"), "UA_ELECT")

        validate = _find_prefix(ElectiveURL.Validate)
        self.assertTrue(validate, "missing validate.do capture")
        self.assertEqual(validate[0]["headers"].get("Referer"), ElectiveURL.SupplyCancel)
        self.assertEqual(validate[0]["headers"].get("User-Agent"), "UA_ELECT")

        electsupp = [r for r in captured if r["url"].startswith("https://elective.pku.edu.cn/") and "electSupplement.do" in r["url"]]
        self.assertTrue(electsupp, "missing electSupplement.do capture")
        self.assertEqual(electsupp[0]["headers"].get("Referer"), ElectiveURL.SupplyCancel)
        self.assertEqual(electsupp[0]["headers"].get("User-Agent"), "UA_ELECT")

        # IAAA UA is set and stable across requests
        iaaa_req = _find_contains("iaaa.pku.edu.cn")
        self.assertTrue(iaaa_req, "missing IAAA request capture")
        self.assertTrue(all(r["headers"].get("User-Agent") == "UA_IAAA" for r in iaaa_req))


if __name__ == "__main__":
    unittest.main()
