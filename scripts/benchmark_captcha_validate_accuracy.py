#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Online captcha benchmark (real DrawServlet + Recognize + Validate).

This gives a more realistic signal than offline synthetic captchas:
- exact accuracy is measured by the server-side Validate() result
- latency is measured end-to-end (Draw + Recognize + Validate)

Recommended usage:
Run during the "UI already open" phase (e.g. 抽签阶段/非峰值)，设置较大的 sleep，避免触发频控。
"""

from __future__ import annotations

import argparse
import statistics
import sys
import os
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[max(0, min(k, len(values) - 1))]


def _fmt_ms(x):
    if x is None:
        return "--"
    return "%.1f" % x


def _summarize_ms(vals):
    if not vals:
        return {}
    return {
        "n": len(vals),
        "avg": statistics.mean(vals),
        "p50": _percentile(vals, 50),
        "p90": _percentile(vals, 90),
        "p95": _percentile(vals, 95),
        "max": max(vals),
    }


def _print_stats(name, st):
    if not st:
        print(name + ": n/a")
        return
    print(
        f"{name}: avg={_fmt_ms(st['avg'])} p50={_fmt_ms(st['p50'])} "
        f"p90={_fmt_ms(st['p90'])} p95={_fmt_ms(st['p95'])} max={_fmt_ms(st['max'])} (ms)"
    )


def _login(cfg):
    import random
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
    parser = argparse.ArgumentParser(description="Online captcha accuracy benchmark via Validate().")
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="config.ini path (optional). If set, overrides AUTOELECTIVE_CONFIG_INI for this process.",
    )
    parser.add_argument(
        "--providers",
        default=None,
        help="comma-separated providers (default: config provider + fallbacks)",
    )
    parser.add_argument("--samples", type=int, default=20, help="samples per provider")
    parser.add_argument("--sleep", type=float, default=0.5, help="sleep seconds between samples")
    args = parser.parse_args()

    if args.config:
        from autoelective.environ import Environ

        Environ().config_ini = args.config

    from autoelective.config import AutoElectiveConfig
    from autoelective.captcha import get_recognizer
    from autoelective.exceptions import (
        NotInOperationTimeError,
        SessionExpiredError,
        InvalidTokenError,
        NoAuthInfoError,
        SharedSessionError,
        OperationTimeoutError,
        OperationFailedError,
        RecognizerError,
    )

    cfg = AutoElectiveConfig()
    providers = None
    if args.providers:
        providers = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    else:
        providers = [cfg.captcha_provider] + cfg.captcha_fallback_providers
    seen = set()
    providers = [p for p in providers if p and not (p in seen or seen.add(p))]

    elect = _login(cfg)

    for p in providers:
        recognizer = get_recognizer(p)
        ok = 0
        fail = 0
        errors = 0
        draw_ms = []
        recog_ms = []
        val_ms = []
        total_ms = []

        print("\n== provider:", p, "==")
        for _ in range(max(0, int(args.samples))):
            try:
                t0 = time.time()
                r = elect.get_DrawServlet()
                t1 = time.time()
                draw_dt = (t1 - t0) * 1000.0
                draw_ms.append(draw_dt)

                t2 = time.time()
                cap = recognizer.recognize(r.content)
                t3 = time.time()
                recog_dt = (t3 - t2) * 1000.0
                recog_ms.append(recog_dt)

                t4 = time.time()
                rr = elect.get_Validate(cfg.iaaa_id, cap.code)
                t5 = time.time()
                val_dt = (t5 - t4) * 1000.0
                val_ms.append(val_dt)

                total_ms.append(draw_dt + recog_dt + val_dt)

                try:
                    valid = rr.json().get("valid")
                except Exception:
                    valid = None
                if valid == "2":
                    ok += 1
                elif valid == "0":
                    fail += 1
                else:
                    errors += 1
            except NotInOperationTimeError as e:
                print("Not in operation time:", e)
                break
            except (
                SessionExpiredError,
                InvalidTokenError,
                NoAuthInfoError,
                SharedSessionError,
                OperationTimeoutError,
            ) as e:
                print("Auth/session error:", e)
                break
            except (RecognizerError, OperationFailedError) as e:
                errors += 1
            except Exception as e:
                errors += 1
            if args.sleep:
                time.sleep(max(0.0, float(args.sleep)))

        attempts = ok + fail + errors
        print("attempts:", attempts, "ok:", ok, "fail:", fail, "errors:", errors)
        if attempts:
            print("validate_pass_rate:", "%.3f" % (ok / attempts))
        _print_stats("draw", _summarize_ms(draw_ms))
        _print_stats("recognize", _summarize_ms(recog_ms))
        _print_stats("validate", _summarize_ms(val_ms))
        _print_stats("total", _summarize_ms(total_ms))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
