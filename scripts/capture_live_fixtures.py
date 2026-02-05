#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Capture live PKU elective HTML/JSON responses into local fixtures (with sanitization).

This is meant to be used during the "UI is open but not the peak抢课 window" stage:
- capture real HTML (SupplyCancel / Supplement / tips pages)
- keep frequency low and safe (sleep between requests)
- output both raw and sanitized copies to avoid leaking sensitive info

All outputs go to cache/ by default and are ignored by git.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _mkdirp(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _guess_ext(content_type: str | None, raw: bytes) -> str:
    ct = (content_type or "").lower()
    if "application/json" in ct:
        return "json"
    if "text/html" in ct or "application/xhtml" in ct or raw.lstrip().startswith(b"<"):
        return "html"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8"):
        return "jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return "bin"


def _safe_headers(headers: dict) -> dict:
    # Keep only response headers helpful for debugging parsing/encoding.
    allow = {"content-type", "content-length", "date", "server"}
    out = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in allow:
            out[lk] = str(v)
    return out


def _login(cfg):
    from autoelective.iaaa import IAAAClient
    from autoelective.elective import ElectiveClient
    from autoelective.const import USER_AGENT_LIST
    from autoelective.parser import get_sida

    user_agent = random.choice(USER_AGENT_LIST)

    iaaa = IAAAClient(timeout=cfg.iaaa_client_timeout)
    iaaa.set_user_agent(user_agent)
    iaaa.oauth_home()
    r = iaaa.oauth_login(cfg.iaaa_id, cfg.iaaa_password)
    token = r.json()["token"]

    elect = ElectiveClient(id=0, timeout=cfg.elective_client_timeout)
    elect.clear_cookies()
    elect.set_user_agent(user_agent)
    r = elect.sso_login(token)
    if cfg.is_dual_degree:
        sida = get_sida(r)
        elect.sso_login_dual_degree(sida, cfg.identity, r.url)
    return elect


def _save_one(
    out_raw: str,
    out_sanitized: str,
    idx: int,
    name: str,
    url: str,
    status_code: int,
    headers: dict,
    content: bytes,
    student_id: str | None,
    sanitize: bool,
):
    from autoelective.fixtures import redact_url, sanitize_bytes

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ct = (headers or {}).get("Content-Type") or (headers or {}).get("content-type") or ""
    ext = _guess_ext(ct, content)
    stem = f"{idx:03d}_{name}_{ts}"

    raw_path = os.path.join(out_raw, f"{stem}.{ext}")
    raw_meta = os.path.join(out_raw, f"{stem}.meta.json")
    with open(raw_path, "wb") as fp:
        fp.write(content or b"")
    meta = {
        "name": name,
        "ts": ts,
        "url": redact_url(url, student_id=student_id),
        "status_code": int(status_code),
        "headers": _safe_headers(headers),
        "path": os.path.basename(raw_path),
        "bytes": int(len(content or b"")),
    }
    with open(raw_meta, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)

    if not sanitize:
        return

    sanitized_path = os.path.join(out_sanitized, f"{stem}.{ext}")
    sanitized_meta = os.path.join(out_sanitized, f"{stem}.meta.json")
    sanitized = sanitize_bytes(content or b"", content_type=ct, student_id=student_id)
    with open(sanitized_path, "wb") as fp:
        fp.write(sanitized)
    with open(sanitized_meta, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Capture live PKU elective fixtures (raw + sanitized).")
    parser.add_argument("-c", "--config", default=None, help="config.ini path (optional)")
    parser.add_argument("--out", default="cache/live_fixtures", help="output directory (default: cache/live_fixtures)")
    parser.add_argument("--sanitize", action="store_true", help="also write sanitized fixtures")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between requests")
    parser.add_argument("--pages", type=int, default=1, help="capture SupplyCancel + Supplement pages up to N (N>=1)")
    parser.add_argument("--help-only", action="store_true", help="only capture HelpController")
    parser.add_argument("--draw-count", type=int, default=0, help="capture N DrawServlet responses")
    args = parser.parse_args()

    # Set config path before importing AutoElectiveConfig (singleton).
    if args.config:
        from autoelective.environ import Environ

        Environ().config_ini = args.config

    from autoelective.config import AutoElectiveConfig

    cfg = AutoElectiveConfig()
    student_id = cfg.iaaa_id

    out_raw = os.path.join(args.out, "raw")
    out_sanitized = os.path.join(args.out, "sanitized")
    _mkdirp(out_raw)
    if args.sanitize:
        _mkdirp(out_sanitized)

    elect = _login(cfg)

    idx = 0

    def _capture(resp, name: str):
        nonlocal idx
        idx += 1
        _save_one(
            out_raw=out_raw,
            out_sanitized=out_sanitized,
            idx=idx,
            name=name,
            url=getattr(resp, "url", ""),
            status_code=getattr(resp, "status_code", 0),
            headers=getattr(resp, "headers", {}) or {},
            content=getattr(resp, "content", b"") or b"",
            student_id=student_id,
            sanitize=args.sanitize,
        )
        if args.sleep:
            time.sleep(max(0.0, float(args.sleep)))

    # Always capture HelpController once; this includes schedule datagrid.
    r = elect.get_HelpController()
    _capture(r, "helpcontroller")

    if args.help_only:
        print("Saved to:", args.out)
        return 0

    # Capture SupplyCancel + following pages.
    r = elect.get_SupplyCancel(student_id)
    _capture(r, "supplycancel")

    pages = max(1, int(args.pages))
    for p in range(2, pages + 1):
        r = elect.get_supplement(student_id, page=p)
        _capture(r, f"supplement_p{p}")

    for i in range(max(0, int(args.draw_count))):
        r = elect.get_DrawServlet()
        _capture(r, f"drawservlet_{i+1}")

    print("Saved to:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

