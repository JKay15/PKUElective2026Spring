#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utilities for capturing/sanitizing live HTTP responses into shareable fixtures.

We keep this module intentionally small and dependency-free so it can be used
both by scripts and by offline tests.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_RE_SIDA = re.compile(r"(?i)(sida=)([0-9a-f]{32})")
_RE_TOKEN = re.compile(r"(?i)(token=)([^&\s]+)")
_RE_JSESSIONID = re.compile(r"(?i)(JSESSIONID=)([^;\s]+)")
_RE_PHPSESSID = re.compile(r"(?i)(PHPSESSID=)([^;\s]+)")
_RE_XH_PARAM = re.compile(r"(?i)(\bxh=)(\d+)")


def sanitize_text(text: str, student_id: str | None = None) -> str:
    if text is None:
        return ""
    s = str(text)

    # Most sensitive value in PKU elective pages/urls is student_id (xh).
    if student_id:
        s = s.replace(student_id, "STUDENT_ID")

    # Common query params / cookies that should never be committed.
    s = _RE_XH_PARAM.sub(r"\1STUDENT_ID", s)
    s = _RE_SIDA.sub(r"\1SIDA", s)
    s = _RE_TOKEN.sub(r"\1TOKEN", s)
    s = _RE_JSESSIONID.sub(r"\1JSESSIONID", s)
    s = _RE_PHPSESSID.sub(r"\1PHPSESSID", s)
    return s


def redact_url(url: str, student_id: str | None = None) -> str:
    """
    Redact sensitive query parameters from a url string.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        qs = parse_qsl(parts.query, keep_blank_values=True)
        new_qs = []
        for k, v in qs:
            lk = (k or "").lower()
            if lk in {"token", "sida", "xh", "student_id"}:
                new_qs.append((k, "REDACTED"))
                continue
            if student_id and v == student_id:
                new_qs.append((k, "REDACTED"))
                continue
            rv = v
            if student_id:
                rv = rv.replace(student_id, "STUDENT_ID")
            rv = sanitize_text(rv, student_id=None)
            new_qs.append((k, rv))
        query = urlencode(new_qs, doseq=True)
        # Drop fragment unconditionally for stability.
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    except Exception:
        return sanitize_text(url, student_id=student_id)


def _looks_like_text(raw: bytes, content_type: str | None = None) -> bool:
    ct = (content_type or "").lower()
    if any(x in ct for x in ("text/", "application/json", "application/javascript", "xml")):
        return True
    if not raw:
        return True
    head = raw[:64].lstrip()
    # Cheap heuristic: html/json.
    return head.startswith((b"<", b"{", b"["))


def sanitize_bytes(raw: bytes, content_type: str | None = None, student_id: str | None = None) -> bytes:
    if raw is None:
        return b""
    if not _looks_like_text(raw, content_type=content_type):
        return raw
    try:
        text = raw.decode("utf-8")
    except Exception:
        # Requests may decode gbk into .text, but for fixtures we only need a readable,
        # redacted payload; replacement keeps it robust.
        text = raw.decode("utf-8", errors="replace")
    redacted = sanitize_text(text, student_id=student_id)
    return redacted.encode("utf-8")

