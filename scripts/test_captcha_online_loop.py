#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Online captcha loop stability test (no elect).

Flow per round:
    DrawServlet -> OCR -> validate.do

Use this to verify captcha chain stability even when no course is available.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _login(cfg):
    from autoelective.const import USER_AGENT_LIST
    from autoelective.iaaa import IAAAClient
    from autoelective.elective import ElectiveClient
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


def main():
    parser = argparse.ArgumentParser(
        description="Online captcha OCR loop stability test: Draw -> OCR -> Validate (no elect)."
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="config.ini path (optional). If set, overrides AUTOELECTIVE_CONFIG_INI for this process.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="captcha provider/model (default: captcha.provider in config)",
    )
    parser.add_argument("--rounds", type=int, default=60, help="test rounds")
    parser.add_argument("--sleep", type=float, default=0.5, help="sleep seconds between rounds")
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=20,
        help="stop when consecutive errors reach this threshold",
    )
    parser.add_argument(
        "--show-code",
        action="store_true",
        help="print recognized captcha code for each round",
    )
    args = parser.parse_args()

    if args.config:
        from autoelective.environ import Environ

        Environ().config_ini = args.config

    from autoelective.config import AutoElectiveConfig
    from autoelective.captcha import get_recognizer
    from autoelective.exceptions import (
        SessionExpiredError,
        InvalidTokenError,
        NoAuthInfoError,
        SharedSessionError,
        OperationTimeoutError,
        OperationFailedError,
        RecognizerError,
        NotInOperationTimeError,
    )

    cfg = AutoElectiveConfig()
    provider = (args.provider or cfg.captcha_provider or "").strip().lower()
    if not provider:
        print("[ERROR] empty provider")
        return 2

    print("=== Online Captcha Loop Stability Test ===")
    print("provider:", provider)
    print("rounds:", int(args.rounds))
    print("sleep:", float(args.sleep))
    print("max_consecutive_errors:", int(args.max_consecutive_errors))
    print("")

    try:
        recognizer = get_recognizer(provider)
    except Exception as e:
        print("[ERROR] failed to build recognizer:", e)
        return 2

    try:
        elect = _login(cfg)
    except Exception as e:
        print("[ERROR] login failed:", e)
        return 2

    ok = 0
    fail = 0
    unknown = 0
    errors = 0
    consecutive_errors = 0

    rounds = max(0, int(args.rounds))
    for i in range(1, rounds + 1):
        t0 = time.time()
        try:
            r = elect.get_DrawServlet()
            cap = recognizer.recognize(r.content)
            rr = elect.get_Validate(cfg.iaaa_id, cap.code)
            try:
                valid = rr.json().get("valid")
            except Exception:
                valid = None

            dt = time.time() - t0
            code_part = (" code=%s" % cap.code) if args.show_code else ""
            if valid == "2":
                ok += 1
                consecutive_errors = 0
                print("[ROUND %d/%d] PASS%s (%.3fs)" % (i, rounds, code_part, dt))
            elif valid == "0":
                fail += 1
                consecutive_errors = 0
                print("[ROUND %d/%d] FAIL%s (%.3fs)" % (i, rounds, code_part, dt))
            else:
                unknown += 1
                consecutive_errors = 0
                print("[ROUND %d/%d] UNKNOWN valid=%r%s (%.3fs)" % (i, rounds, valid, code_part, dt))
        except NotInOperationTimeError as e:
            print("[STOP] not in operation time:", e)
            break
        except (
            SessionExpiredError,
            InvalidTokenError,
            NoAuthInfoError,
            SharedSessionError,
        ) as e:
            print("[STOP] auth/session error:", e)
            return 2
        except (RecognizerError, OperationFailedError, OperationTimeoutError, Exception) as e:
            errors += 1
            consecutive_errors += 1
            dt = time.time() - t0
            print("[ROUND %d/%d] ERROR (%s) %.3fs" % (i, rounds, e.__class__.__name__, dt))
            if consecutive_errors >= max(1, int(args.max_consecutive_errors)):
                print("[STOP] too many consecutive errors")
                return 1
        if args.sleep > 0:
            time.sleep(float(args.sleep))

    total = ok + fail + unknown + errors
    print("")
    print("=== Summary ===")
    print("total:", total)
    print("pass:", ok)
    print("fail:", fail)
    print("unknown:", unknown)
    print("errors:", errors)
    if total > 0:
        print("pass_rate:", "%.3f" % (ok / total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
