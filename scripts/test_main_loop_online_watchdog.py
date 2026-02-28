#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Online main-loop watchdog test.

It starts `main.py -m` with your config, then polls monitor endpoints:
  - /stat/loop
  - /stat/runtime

Use this during non-peak periods to verify:
  1) main loops keep advancing (no stall),
  2) loop threads stay alive,
  3) optional captcha probe is really producing online OCR attempts.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _fetch_json(url: str, timeout: float = 3.0):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _stop_process(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=8)
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _as_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Start main.py in monitor mode and verify online loop liveness "
            "(stall/thread/probe checks)."
        )
    )
    parser.add_argument("-c", "--config", required=True, help="Path to config.ini")
    parser.add_argument("--duration", type=float, default=180.0, help="watch duration seconds")
    parser.add_argument("--poll", type=float, default=2.0, help="poll interval seconds")
    parser.add_argument(
        "--stall-seconds",
        type=float,
        default=30.0,
        help="fail if elective_loop does not advance for this many seconds",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="max wait for monitor endpoint to be ready",
    )
    parser.add_argument(
        "--with-preflight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run main.py with --preflight",
    )
    parser.add_argument(
        "--require-probe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="require probe_attempt to increase during the run",
    )
    args = parser.parse_args()

    cfg = Path(args.config).expanduser().resolve()
    if not cfg.is_file():
        print("[ERROR] config not found:", cfg)
        return 2

    # Load monitor host/port from the same config file.
    os.environ["AUTOELECTIVE_CONFIG_INI"] = str(cfg)
    from autoelective.config import AutoElectiveConfig
    from autoelective.utils import Singleton

    Singleton._inst.pop(AutoElectiveConfig, None)
    try:
        conf = AutoElectiveConfig()
    except Exception as e:
        print("[ERROR] failed to load config:", e)
        return 2

    monitor_base = "http://%s:%s" % (conf.monitor_host, conf.monitor_port)
    loop_url = monitor_base + "/stat/loop"
    runtime_url = monitor_base + "/stat/runtime"

    if args.require_probe and not bool(conf.captcha_probe_enabled):
        print("[ERROR] --require-probe is on, but [captcha] probe_enabled=false in config.")
        print("        Set probe_enabled=true to verify no-course online OCR loop.")
        return 2

    cmd = [sys.executable, str(REPO_ROOT / "main.py"), "-c", str(cfg), "-m"]
    if args.with_preflight:
        cmd.append("--preflight")

    print("=== Main Loop Online Watchdog ===")
    print("config:", str(cfg))
    print("monitor:", monitor_base)
    print("duration:", float(args.duration))
    print("poll:", float(args.poll))
    print("stall_seconds:", float(args.stall_seconds))
    print("require_probe:", bool(args.require_probe))
    print("command:", " ".join(cmd))
    print("")

    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=os.environ.copy())
    start = time.time()

    last_elective_loop = None
    last_advance_at = time.time()
    startup_ok = False
    startup_deadline = time.time() + max(1.0, float(args.startup_timeout))

    probe_start = 0
    probe_last = 0
    fetch_errors = 0

    try:
        # Wait monitor ready.
        while time.time() < startup_deadline:
            if proc.poll() is not None:
                print("[FAIL] main process exited early with code:", proc.returncode)
                return 1
            try:
                d_loop = _fetch_json(loop_url)
                d_rt = _fetch_json(runtime_url)
                startup_ok = True
                last_elective_loop = _as_int(d_loop.get("elective_loop"), 0)
                last_advance_at = time.time()
                probe_start = _as_int((d_rt.get("stats") or {}).get("probe_attempt"), 0)
                probe_last = probe_start
                break
            except Exception:
                time.sleep(0.5)

        if not startup_ok:
            print("[FAIL] monitor did not become ready within startup timeout")
            return 1

        deadline = start + max(1.0, float(args.duration))
        poll = max(0.2, float(args.poll))
        stall_seconds = max(1.0, float(args.stall_seconds))

        while time.time() < deadline:
            if proc.poll() is not None:
                print("[FAIL] main process exited during test, code:", proc.returncode)
                return 1

            now = time.time()
            try:
                d_loop = _fetch_json(loop_url)
                d_rt = _fetch_json(runtime_url)
                fetch_errors = 0
            except Exception as e:
                fetch_errors += 1
                print("[WARN] monitor fetch error x%d: %s" % (fetch_errors, e))
                if fetch_errors >= 5:
                    print("[FAIL] monitor fetch failed too many times")
                    return 1
                time.sleep(poll)
                continue

            iaaa_alive = bool(d_loop.get("iaaa_loop_is_alive"))
            elective_alive = bool(d_loop.get("elective_loop_is_alive"))
            iaaa_loop = _as_int(d_loop.get("iaaa_loop"), 0)
            elective_loop = _as_int(d_loop.get("elective_loop"), 0)
            stats = d_rt.get("stats") or {}
            probe_attempt = _as_int(stats.get("probe_attempt"), 0)
            captcha_attempt = _as_int(stats.get("captcha_attempt"), 0)

            if not iaaa_alive or not elective_alive:
                print(
                    "[FAIL] loop thread down: iaaa_alive=%s elective_alive=%s"
                    % (iaaa_alive, elective_alive)
                )
                return 1

            if last_elective_loop is None or elective_loop > last_elective_loop:
                last_elective_loop = elective_loop
                last_advance_at = now
            elif now - last_advance_at > stall_seconds:
                print(
                    "[FAIL] elective_loop stalled for %.1fs (value=%s)"
                    % (now - last_advance_at, elective_loop)
                )
                return 1

            probe_last = probe_attempt

            print(
                "[OK] iaaa_loop=%d elective_loop=%d captcha_attempt=%d probe_attempt=%d"
                % (iaaa_loop, elective_loop, captcha_attempt, probe_attempt)
            )
            time.sleep(poll)

        # Final check.
        d_rt = _fetch_json(runtime_url)
        stats = d_rt.get("stats") or {}
        probe_end = _as_int(stats.get("probe_attempt"), probe_last)
        if args.require_probe and probe_end <= probe_start:
            print(
                "[FAIL] probe_attempt did not increase (start=%d, end=%d)"
                % (probe_start, probe_end)
            )
            return 1

        print("")
        print("[PASS] watchdog finished without stall/crash")
        print(
            "probe_attempt_delta:",
            int(probe_end - probe_start),
        )
        return 0
    finally:
        _stop_process(proc)


if __name__ == "__main__":
    raise SystemExit(main())
