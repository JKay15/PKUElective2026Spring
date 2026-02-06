#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from autoelective.config import AutoElectiveConfig
from autoelective.preflight import run_preflight
from autoelective.utils import Singleton


def _fmt_issue(i) -> str:
    kp = i.key_path or "-"
    return f"{i.level} {i.code} [{kp}] {i.message}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Static config preflight (no network, no OCR instantiation).")
    parser.add_argument("-c", "--config", required=True, help="Path to config.ini to validate.")
    parser.add_argument("--strict", action="store_true", help="Treat WARN as failure (exit 1).")
    args = parser.parse_args(argv)

    cfg = Path(args.config).expanduser().resolve()
    if not cfg.is_file():
        print("[ERROR] config not found:", cfg)
        return 2

    # Ensure this process reads the intended config.
    os.environ["AUTOELECTIVE_CONFIG_INI"] = str(cfg)
    Singleton._inst.pop(AutoElectiveConfig, None)

    try:
        config = AutoElectiveConfig()
    except Exception as e:
        print("[ERROR] Failed to load config:", e)
        return 2

    try:
        provider = (config.captcha_provider or "").strip().lower()
    except Exception:
        provider = "unknown"
    try:
        fallbacks = list(config.captcha_fallback_providers or [])
    except Exception:
        fallbacks = []

    issues = run_preflight(config)
    errors = [i for i in issues if i.level == "ERROR"]
    warns = [i for i in issues if i.level == "WARN"]

    print("=== AutoElective Preflight ===")
    print("config:", str(cfg))
    print("captcha.provider:", provider or "(empty)")
    print("captcha.fallback_providers:", ",".join(fallbacks) if fallbacks else "(none)")
    print("strict:", "true" if args.strict else "false")
    print("")

    if errors:
        print("ERRORS (%d):" % len(errors))
        for i in errors:
            print(" -", _fmt_issue(i))
    else:
        print("ERRORS (0)")

    if warns:
        print("WARNINGS (%d):" % len(warns))
        for i in warns:
            print(" -", _fmt_issue(i))
    else:
        print("WARNINGS (0)")

    if errors:
        return 2
    if warns and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
