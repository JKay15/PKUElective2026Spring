#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import os
import re
import subprocess
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _git_ls_files():
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT)
    return [line.strip() for line in out.decode("utf-8", errors="replace").splitlines() if line.strip()]


def _read_text(path):
    with open(path, "rb") as fp:
        raw = fp.read()
    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:12]


class FixtureSecretScanOfflineTest(unittest.TestCase):
    def test_no_tokens_in_tracked_fixtures_and_docs(self):
        # Scan only tracked files to prevent leaking local config/apikeys.
        files = _git_ls_files()

        def _should_scan(p: str) -> bool:
            if p.startswith("tests/fixtures/"):
                return True
            if p.endswith(".md"):
                return True
            if p.endswith(".html") and p.startswith("tests/fixtures/"):
                return True
            if p.endswith(".json") and p.startswith("tests/fixtures/"):
                return True
            return False

        targets = [p for p in files if _should_scan(p)]

        # Only match "key=value" style secrets (avoid false positives on plain words).
        rx = {
            "sida": re.compile(r"(?i)\bsida=([0-9a-f]{32})\b"),
            # Avoid false positives on docs that mention regex like `token=(?!)\\S+`.
            # Real tokens are usually long and start with an alnum.
            "token": re.compile(r"(?i)\btoken=([A-Za-z0-9][^\s&\"']{7,})\b"),
            "xh": re.compile(r"(?i)\bxh=(\d{6,})\b"),
            "jsessionid": re.compile(r"(?i)\bJSESSIONID=([^\s;\"']+)\b"),
        }
        allow = {"SIDA", "TOKEN", "REDACTED", "STUDENT_ID", "JSESSIONID", "PHPSESSID"}

        findings = []
        for rel in targets:
            path = os.path.join(REPO_ROOT, rel)
            if not os.path.isfile(path):
                continue
            text = _read_text(path)
            for name, r in rx.items():
                for m in r.finditer(text):
                    val = m.group(1)
                    if val in allow:
                        continue
                    findings.append(
                        {
                            "file": rel,
                            "kind": name,
                            "sha1": _sha1(val),
                        }
                    )
                    break  # one finding per kind per file is enough

        if findings:
            msg = "Secret-like tokens found in tracked files:\n" + "\n".join(
                "%(file)s kind=%(kind)s sha1=%(sha1)s" % f for f in findings
            )
            self.fail(msg)


if __name__ == "__main__":
    unittest.main()
