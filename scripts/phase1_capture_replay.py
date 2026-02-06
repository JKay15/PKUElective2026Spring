#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 1 helper: capture live fixtures, promote sanitized copies, scan for leaks,
and run offline regression tests.

Default flow:
1) unittest (pre)
2) capture_live_fixtures.py --sanitize
3) promote_live_fixtures.py
4) redaction scan on promoted fixtures
5) unittest (post)
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def _run(cmd, env=None) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    print("[RUN]", printable)
    result = subprocess.run(cmd, env=env)
    return int(result.returncode)


def _scan_redaction(dst: Path) -> int:
    patterns = [
        re.compile(r"sida=(?!SIDA)[0-9a-fA-F]{32}"),
        re.compile(r"token=(?!TOKEN)\\S+"),
        re.compile(r"\\bxh=\\d{6,}"),
    ]
    leaked = []
    for path in dst.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            if pat.search(text):
                leaked.append(path)
                break
    if leaked:
        print("[ERROR] Potential sensitive tokens detected in promoted fixtures:")
        for p in leaked:
            print(" -", p)
        return 3
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Phase 1 capture + replay + regression runner.")
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="config.ini path (required). Also set as AUTOELECTIVE_CONFIG_INI.",
    )
    parser.add_argument("--pages", type=int, default=3, help="supplycancel pages to capture")
    parser.add_argument("--draw-count", type=int, default=5, help="DrawServlet samples")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between requests")
    parser.add_argument(
        "--dst",
        default="tests/fixtures/2026_phase1",
        help="fixture destination for promote step",
    )
    parser.add_argument(
        "--names",
        default="helpcontroller,supplycancel,supplement_p2",
        help="fixture names for promote step (comma-separated)",
    )
    parser.add_argument("--strict", action="store_true", help="require all names to exist")
    parser.add_argument("--force", action="store_true", help="overwrite existing fixtures")
    parser.add_argument("--skip-unittest", action="store_true", help="skip unittest runs")
    args = parser.parse_args(argv)

    cfg = Path(args.config)
    if not cfg.is_file():
        print("[ERROR] config not found:", cfg)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    py = sys.executable
    env = os.environ.copy()
    env["AUTOELECTIVE_CONFIG_INI"] = str(cfg)

    if not args.skip_unittest:
        rc = _run([py, "-m", "unittest", "-q"], env=env)
        if rc != 0:
            return rc

    rc = _run(
        [
            py,
            str(repo_root / "scripts" / "capture_live_fixtures.py"),
            "-c",
            str(cfg),
            "--sanitize",
            "--pages",
            str(args.pages),
            "--draw-count",
            str(args.draw_count),
            "--sleep",
            str(args.sleep),
        ],
        env=env,
    )
    if rc != 0:
        return rc

    promote_cmd = [
        py,
        str(repo_root / "scripts" / "promote_live_fixtures.py"),
        "--src",
        str(repo_root / "cache" / "live_fixtures" / "sanitized"),
        "--dst",
        str(repo_root / args.dst),
        "--names",
        args.names,
    ]
    if args.strict:
        promote_cmd.append("--strict")
    if args.force:
        promote_cmd.append("--force")

    rc = _run(promote_cmd, env=env)
    if rc != 0:
        return rc

    rc = _scan_redaction(Path(repo_root / args.dst))
    if rc != 0:
        return rc

    if not args.skip_unittest:
        rc = _run([py, "-m", "unittest", "-q"], env=env)
        if rc != 0:
            return rc

    print("[OK] Phase 1 capture + promote + replay completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
