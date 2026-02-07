#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 1 prestart helper: run the must-run checks in a deterministic order and
archive full outputs under cache/prestart/ for later review.

This script does NOT:
- perform any elective submission
- change main loop behaviors
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _mkdirp(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _run_to_file(cmd: list[str], out_file: Path, env: dict[str, str] | None = None) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    print("[RUN]", printable)
    with out_file.open("w", encoding="utf-8", errors="replace") as fp:
        fp.write("[CMD] " + printable + "\n")
        fp.write("[TIME] " + time.strftime("%Y-%m-%d %H:%M:%S %z") + "\n\n")
        fp.flush()
        p = subprocess.run(cmd, stdout=fp, stderr=subprocess.STDOUT, env=env)
        rc = int(p.returncode)
        fp.write("\n\n[EXIT] %d\n" % rc)
        fp.flush()
    if rc == 0:
        print("[OK] rc=0 ->", out_file)
    else:
        print("[FAIL] rc=%d -> %s" % (rc, out_file))
    return rc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Phase 1 prestart checks (offline-first + archived outputs).")
    parser.add_argument("-c", "--config", required=True, help="config.ini path to validate and use for tests.")
    parser.add_argument(
        "--baseline",
        default="baseline-footprint",
        help="baseline git commit/tag for audit (default: baseline-footprint)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat WARN as failure in preflight (pass --strict to scripts/preflight_config.py).",
    )
    parser.add_argument("--skip-unittest", action="store_true", help="Skip unittest run (not recommended).")
    args = parser.parse_args(argv)

    cfg = Path(args.config).expanduser().resolve()
    if not cfg.is_file():
        print("[ERROR] config not found:", cfg)
        return 2

    ts = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    out_dir = Path(REPO_ROOT) / "cache" / "prestart" / ts
    _mkdirp(out_dir)

    py = sys.executable
    env = os.environ.copy()
    env["AUTOELECTIVE_CONFIG_INI"] = str(cfg)

    meta = {
        "ts": ts,
        "repo_root": REPO_ROOT,
        "python": py,
        "config": str(cfg),
        "baseline": args.baseline,
        "steps": [],
    }

    overall = 0

    # Step 1: preflight (static, no network)
    preflight_cmd = [py, str(Path(REPO_ROOT) / "scripts" / "preflight_config.py"), "-c", str(cfg)]
    if args.strict:
        preflight_cmd.append("--strict")
    rc = _run_to_file(preflight_cmd, out_dir / "preflight.txt", env=env)
    meta["steps"].append({"name": "preflight", "rc": rc, "out": "preflight.txt"})
    overall = max(overall, rc)

    # Step 2: unittest (offline regressions)
    if not args.skip_unittest:
        rc = _run_to_file([py, "-m", "unittest", "-q"], out_dir / "unittest.txt", env=env)
        meta["steps"].append({"name": "unittest", "rc": rc, "out": "unittest.txt"})
        overall = max(overall, rc)

    # Step 3: baseline audit (offline)
    rc = _run_to_file(
        [py, str(Path(REPO_ROOT) / "scripts" / "audit_baseline_footprint.py"), "--baseline", str(args.baseline)],
        out_dir / "audit_baseline_footprint.txt",
        env=env,
    )
    meta["steps"].append({"name": "audit_baseline_footprint", "rc": rc, "out": "audit_baseline_footprint.txt"})
    overall = max(overall, rc)

    with (out_dir / "meta.json").open("w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)

    print("")
    print("=== Prestart Check Summary ===")
    print("out_dir:", str(out_dir))
    for s in meta["steps"]:
        print(" - %s rc=%s out=%s" % (s["name"], s["rc"], s["out"]))
    print("exit:", overall)
    return int(overall)


if __name__ == "__main__":
    raise SystemExit(main())
