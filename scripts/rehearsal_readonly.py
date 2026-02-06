#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Read-only rehearsal runner.

Goal: in "not in operation time" stage, verify that the login chain is still OK,
capture HelpController (and optionally SupplyCancel / Draw / Validate) into cache/,
and produce a stable summary.json for later comparison.

Hard constraints:
- Never call electSupplement.
- Default is minimal traffic (HelpController only).
- All outputs are written under cache/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run(cmd: list[str], env: dict[str, str]) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    print("[RUN]", printable)
    return int(subprocess.run(cmd, env=env).returncode)


def _mkdirp(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


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
    allow = {"content-type", "content-length", "date", "server"}
    out = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in allow:
            out[lk] = str(v)
    return out


def _looks_like_html(resp) -> bool:
    try:
        ctype = resp.headers.get("Content-Type") or resp.headers.get("content-type") or ""
    except Exception:
        ctype = ""
    if isinstance(ctype, str) and ("text/html" in ctype.lower() or "application/xhtml" in ctype.lower()):
        return True
    raw = getattr(resp, "content", b"") or b""
    return raw.lstrip().startswith(b"<")


def _save_response(
    out_raw: Path,
    out_sanitized: Path,
    idx: int,
    name: str,
    resp,
    student_id: Optional[str],
    sanitize: bool,
    extra_meta: Optional[dict] = None,
) -> dict:
    from autoelective.fixtures import redact_url, sanitize_bytes

    url = getattr(resp, "url", "") or ""
    status_code = int(getattr(resp, "status_code", 0) or 0)
    headers = getattr(resp, "headers", {}) or {}
    content = getattr(resp, "content", b"") or b""
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    ext = _guess_ext(ct, content)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stem = f"{idx:03d}_{name}_{ts}"

    raw_path = out_raw / f"{stem}.{ext}"
    meta_path = out_raw / f"{stem}.meta.json"
    raw_path.write_bytes(content)

    meta = {
        "name": name,
        "ts": ts,
        "url": redact_url(url, student_id=student_id),
        "status_code": status_code,
        "headers": _safe_headers(headers),
        "path": raw_path.name,
        "bytes": int(len(content)),
    }
    if extra_meta:
        meta.update(extra_meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if sanitize:
        sanitized_path = out_sanitized / f"{stem}.{ext}"
        sanitized_meta = out_sanitized / f"{stem}.meta.json"
        sanitized = sanitize_bytes(content, content_type=str(ct), student_id=student_id)
        sanitized_path.write_bytes(sanitized)
        sanitized_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta


def _latency_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    xs = sorted(float(x) for x in values)
    n = len(xs)
    avg = sum(xs) / n
    if n % 2 == 1:
        med = xs[n // 2]
    else:
        med = 0.5 * (xs[n // 2 - 1] + xs[n // 2])
    return {
        "count": n,
        "avg_s": avg,
        "median_s": med,
        "max_s": xs[-1],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only rehearsal (no electSupplement).")
    parser.add_argument("-c", "--config", required=True, help="config.ini path (required)")
    parser.add_argument("--help-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--attempt-supplycancel", action="store_true", help="GET SupplyCancel (read-only)")
    parser.add_argument("--attempt-draw", action="store_true", help="GET DrawServlet (read-only)")
    parser.add_argument("--draw-count", type=int, default=1, help="DrawServlet attempts (default: 1)")
    parser.add_argument("--attempt-validate", action="store_true", help="POST validate.do with dummy code (read-only)")
    parser.add_argument("--validate-count", type=int, default=1, help="Validate attempts (default: 1)")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between requests")
    parser.add_argument("--sanitize", action=argparse.BooleanOptionalAction, default=True, help="also write sanitized copies")
    parser.add_argument("--strict", action="store_true", help="treat NotInOperationTimeError as failure")
    parser.add_argument("--out", default=None, help="output directory (default: cache/rehearsal/<timestamp>/)")
    args = parser.parse_args(argv)

    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_file():
        print("[ERROR] config not found:", cfg_path)
        return 2

    # Enforce output under cache/ (hard constraint).
    if args.out:
        out_dir = Path(args.out).expanduser()
        if not out_dir.is_absolute():
            out_dir = (REPO_ROOT / out_dir).resolve()
    else:
        ts = time.strftime("%Y%m%dT%H%M%S", time.localtime())
        out_dir = (REPO_ROOT / "cache" / "rehearsal" / ts).resolve()
    cache_root = (REPO_ROOT / "cache").resolve()
    try:
        out_dir.relative_to(cache_root)
    except Exception:
        print("[ERROR] --out must be under cache/ (got %s)" % out_dir)
        return 2

    out_raw = out_dir / "raw"
    out_sanitized = out_dir / "sanitized"
    _mkdirp(out_raw)
    if args.sanitize:
        _mkdirp(out_sanitized)

    # Preflight: fail fast on ERRORs (no network).
    env = os.environ.copy()
    env["AUTOELECTIVE_CONFIG_INI"] = str(cfg_path)
    rc = _run([sys.executable, str(REPO_ROOT / "scripts" / "preflight_config.py"), "-c", str(cfg_path)], env=env)
    if rc != 0:
        print("[ERROR] preflight failed (rc=%d)" % rc)
        return 2

    # If any attempt flags are set, disable help-only automatically.
    help_only = bool(args.help_only)
    if args.attempt_supplycancel or args.attempt_draw or args.attempt_validate:
        help_only = False

    # Import after config path is set.
    from autoelective.environ import Environ

    Environ().config_ini = str(cfg_path)

    from autoelective.config import AutoElectiveConfig
    from autoelective.const import USER_AGENT_LIST
    from autoelective.elective import ElectiveClient
    from autoelective.iaaa import IAAAClient
    from autoelective.parser import get_sida
    from autoelective.rehearsal import classify_rehearsal_error, extract_operation_window

    cfg = AutoElectiveConfig()
    student_id = cfg.iaaa_id

    latencies: dict[str, list[float]] = {}
    events: list[dict[str, Any]] = []
    last_op_window: Optional[str] = None
    strict_only_hits: list[dict[str, Any]] = []
    fatal_hits: list[dict[str, Any]] = []

    def _sleep():
        if args.sleep is None:
            return
        try:
            s = float(args.sleep)
        except Exception:
            return
        if s > 0:
            time.sleep(s)

    def _record_latency(name: str, dt: float) -> None:
        latencies.setdefault(name, []).append(float(dt))

    def _record_exception(name: str, exc: BaseException, dt: float) -> None:
        nonlocal last_op_window
        kind, strict_only = classify_rehearsal_error(exc)
        window = extract_operation_window(exc)
        if window:
            last_op_window = window
        item = {
            "name": name,
            "kind": kind,
            "strict_only": bool(strict_only),
            "latency_s": float(dt),
            "error": repr(exc),
            "operation_window": window,
        }
        events.append(item)
        if strict_only:
            strict_only_hits.append(item)
        else:
            fatal_hits.append(item)

        resp = getattr(exc, "response", None)
        if resp is not None:
            try:
                meta = _save_response(
                    out_raw=out_raw,
                    out_sanitized=out_sanitized,
                    idx=len(events),
                    name=name,
                    resp=resp,
                    student_id=student_id,
                    sanitize=bool(args.sanitize),
                    extra_meta={"error_kind": kind},
                )
                item["saved"] = meta.get("path")
            except Exception as e:
                item["save_error"] = repr(e)

    # 1) Login chain
    user_agent = random.choice(USER_AGENT_LIST)
    login_ok = False
    elect = None
    try:
        t0 = time.monotonic()
        iaaa = IAAAClient(timeout=cfg.iaaa_client_timeout)
        iaaa.set_user_agent(user_agent)
        iaaa.oauth_home()
        _record_latency("iaaa_oauth_home", time.monotonic() - t0)
        events.append({"name": "iaaa_oauth_home", "kind": "ok"})
        _sleep()

        t0 = time.monotonic()
        r = iaaa.oauth_login(student_id, cfg.iaaa_password)
        _record_latency("iaaa_oauth_login", time.monotonic() - t0)
        events.append({"name": "iaaa_oauth_login", "kind": "ok"})
        token = r.json()["token"]
        _sleep()

        elect = ElectiveClient(id=0, timeout=cfg.elective_client_timeout)
        elect.clear_cookies()
        elect.set_user_agent(user_agent)

        t0 = time.monotonic()
        r = elect.sso_login(token)
        _record_latency("elective_sso_login", time.monotonic() - t0)
        events.append({"name": "elective_sso_login", "kind": "ok"})
        _sleep()

        if cfg.is_dual_degree:
            sida = get_sida(r)
            t0 = time.monotonic()
            elect.sso_login_dual_degree(sida, cfg.identity, r.url)
            _record_latency("elective_sso_login_dual_degree", time.monotonic() - t0)
            events.append({"name": "elective_sso_login_dual_degree", "kind": "ok"})
            _sleep()

        login_ok = True
    except Exception as e:
        dt = 0.0
        try:
            dt = float(time.monotonic() - t0)
        except Exception:
            dt = 0.0
        _record_exception("login", e, dt)
        login_ok = False

    if not login_ok or elect is None:
        summary = {
            "ok": False,
            "exit_code": 2,
            "config": str(cfg_path),
            "out": str(out_dir),
            "last_operation_window": last_op_window,
            "latency": {k: _latency_stats(v) for k, v in latencies.items()},
            "events": events,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[ERROR] rehearsal failed at login; output:", out_dir)
        return 2

    # 2) Always GET HelpController once.
    try:
        t0 = time.monotonic()
        r = elect.get_HelpController()
        dt = time.monotonic() - t0
        _record_latency("helpcontroller", dt)
        events.append({"name": "helpcontroller", "kind": "ok", "latency_s": float(dt)})
        _save_response(
            out_raw=out_raw,
            out_sanitized=out_sanitized,
            idx=len(events),
            name="helpcontroller",
            resp=r,
            student_id=student_id,
            sanitize=bool(args.sanitize),
        )
    except Exception as e:
        dt = 0.0
        try:
            dt = float(time.monotonic() - t0)
        except Exception:
            dt = 0.0
        _record_exception("helpcontroller", e, dt)
        summary = {
            "ok": False,
            "exit_code": 2,
            "config": str(cfg_path),
            "out": str(out_dir),
            "last_operation_window": last_op_window,
            "latency": {k: _latency_stats(v) for k, v in latencies.items()},
            "events": events,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[ERROR] HelpController failed; output:", out_dir)
        return 2

    _sleep()

    # 3) Optional read-only endpoints.
    if not help_only and args.attempt_supplycancel:
        try:
            t0 = time.monotonic()
            r = elect.get_SupplyCancel(student_id)
            dt = time.monotonic() - t0
            _record_latency("supplycancel", dt)
            events.append({"name": "supplycancel", "kind": "ok", "latency_s": float(dt)})
            _save_response(
                out_raw=out_raw,
                out_sanitized=out_sanitized,
                idx=len(events),
                name="supplycancel",
                resp=r,
                student_id=student_id,
                sanitize=bool(args.sanitize),
            )
        except Exception as e:
            dt = 0.0
            try:
                dt = float(time.monotonic() - t0)
            except Exception:
                dt = 0.0
            _record_exception("supplycancel", e, dt)
        _sleep()

    if not help_only and args.attempt_draw:
        n = max(0, int(args.draw_count))
        for i in range(n):
            name = f"drawservlet_{i+1}"
            try:
                t0 = time.monotonic()
                r = elect.get_DrawServlet()
                dt = time.monotonic() - t0
                _record_latency("drawservlet", dt)
                events.append({"name": name, "kind": "ok", "latency_s": float(dt)})
                _save_response(
                    out_raw=out_raw,
                    out_sanitized=out_sanitized,
                    idx=len(events),
                    name=name,
                    resp=r,
                    student_id=student_id,
                    sanitize=bool(args.sanitize),
                )
            except Exception as e:
                dt = 0.0
                try:
                    dt = float(time.monotonic() - t0)
                except Exception:
                    dt = 0.0
                _record_exception(name, e, dt)
            _sleep()

    if not help_only and args.attempt_validate:
        from autoelective.hook import check_elective_title, with_etree

        n = max(0, int(args.validate_count))
        dummy_code = "0000"
        for i in range(n):
            name = f"validate_{i+1}"
            try:
                t0 = time.monotonic()
                r = elect.get_Validate(student_id, dummy_code)
                dt = time.monotonic() - t0
                # validate.do uses status-only hook; if it returned a system page, classify it here.
                if _looks_like_html(r):
                    with_etree(r)
                    check_elective_title(r)
                _record_latency("validate", dt)
                event: dict[str, Any] = {"name": name, "kind": "ok", "latency_s": float(dt)}
                try:
                    event["json"] = r.json()
                except Exception as je:
                    event["json_error"] = repr(je)
                events.append(event)
                _save_response(
                    out_raw=out_raw,
                    out_sanitized=out_sanitized,
                    idx=len(events),
                    name=name,
                    resp=r,
                    student_id=student_id,
                    sanitize=bool(args.sanitize),
                )
            except Exception as e:
                dt = 0.0
                try:
                    dt = float(time.monotonic() - t0)
                except Exception:
                    dt = 0.0
                _record_exception(name, e, dt)
            _sleep()

    # 4) Decide exit code
    strict_fail = bool(args.strict) and len(strict_only_hits) > 0
    fatal_fail = len(fatal_hits) > 0
    exit_code = 2 if fatal_fail else (1 if strict_fail else 0)

    if strict_only_hits and not args.strict:
        # Make the "expected state" signal explicit in logs.
        print("[INFO] Not in operation time (expected).")
        if last_op_window:
            print("[INFO] Operation window:", last_op_window)
        else:
            # Keep one representative error string for visibility.
            print("[INFO] Example:", strict_only_hits[0].get("error"))

    summary = {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "config": str(cfg_path),
        "out": str(out_dir),
        "user_agent": user_agent,
        "last_operation_window": last_op_window,
        "latency": {k: _latency_stats(v) for k, v in latencies.items()},
        "events": events,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] rehearsal completed; output:", out_dir)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

