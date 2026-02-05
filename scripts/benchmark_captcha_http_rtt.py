#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import random
import statistics
import time
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from autoelective.config import AutoElectiveConfig
from autoelective.const import USER_AGENT_LIST
from autoelective.iaaa import IAAAClient
from autoelective.elective import ElectiveClient
from autoelective.parser import get_sida
from autoelective.exceptions import (
    OperationFailedError,
    ServerError,
    StatusCodeError,
    NotInOperationTimeError,
)
from requests.exceptions import RequestException


def summarize(latencies):
    if not latencies:
        return {}
    p90 = statistics.quantiles(latencies, n=10)[8] if len(latencies) >= 10 else max(latencies)
    return {
        "count": len(latencies),
        "avg": statistics.mean(latencies),
        "median": statistics.median(latencies),
        "p90": p90,
        "min": min(latencies),
        "max": max(latencies),
    }


def _format_stats(name, stats):
    if not stats:
        return f"{name}: n/a"
    return (
        f"{name}: avg={stats['avg']:.3f}s median={stats['median']:.3f}s "
        f"p90={stats['p90']:.3f}s min={stats['min']:.3f}s max={stats['max']:.3f}s"
    )


def _dummy_code(length):
    length = max(1, int(length))
    return "A" * length


def login(config):
    username = config.iaaa_id
    password = config.iaaa_password
    if not username or not password:
        raise RuntimeError("Missing IAAA credentials in config.ini")

    user_agent = random.choice(USER_AGENT_LIST)
    iaaa = IAAAClient(timeout=config.iaaa_client_timeout)
    iaaa.set_user_agent(user_agent)

    # request elective's home page to get cookies
    iaaa.oauth_home()

    r = iaaa.oauth_login(username, password)
    try:
        token = r.json()["token"]
    except Exception as e:
        raise RuntimeError("Unable to parse IAAA token: %s" % e)

    elective = ElectiveClient(0, timeout=config.elective_client_timeout)
    elective.clear_cookies()
    elective.set_user_agent(user_agent)
    r = elective.sso_login(token)

    if config.is_dual_degree:
        sida = get_sida(r)
        sttp = config.identity
        elective.sso_login_dual_degree(sida, sttp, r.url)

    # warm up once: supply cancel page (not timed). If not in operation time,
    # skip warmup and still try Draw/Validate.
    try:
        elective.get_SupplyCancel(username)
    except NotInOperationTimeError:
        pass
    return elective


def main():
    parser = argparse.ArgumentParser(
        description="Measure captcha HTTP RTT: DrawServlet + Validate (no OCR)."
    )
    parser.add_argument("--samples", type=int, default=20, help="number of iterations")
    parser.add_argument("--sleep", type=float, default=0.05, help="sleep between iterations")
    parser.add_argument(
        "--code-length",
        type=int,
        default=None,
        help="override captcha length for dummy validation code",
    )
    args = parser.parse_args()

    config = AutoElectiveConfig()
    length = args.code_length or config.captcha_code_length
    code = _dummy_code(length)

    try:
        elective = login(config)
    except (RuntimeError, OperationFailedError, ServerError, StatusCodeError, RequestException) as e:
        print("Login failed:", e)
        return 2

    draw_times = []
    validate_times = []
    total_times = []
    validate_parse_fail = 0

    for _ in range(args.samples):
        t0 = time.time()
        r = elective.get_DrawServlet()
        t1 = time.time()
        draw_times.append(t1 - t0)

        t2 = time.time()
        r = elective.get_Validate(config.iaaa_id, code)
        t3 = time.time()
        validate_times.append(t3 - t2)

        try:
            _ = r.json().get("valid")
        except Exception:
            validate_parse_fail += 1

        total_times.append((t1 - t0) + (t3 - t2))
        if args.sleep:
            time.sleep(args.sleep)

    draw_stats = summarize(draw_times)
    val_stats = summarize(validate_times)
    total_stats = summarize(total_times)

    print("\n=== Captcha HTTP RTT (Draw + Validate) ===")
    print("samples:", len(draw_times))
    print(_format_stats("draw", draw_stats))
    print(_format_stats("validate", val_stats))
    print(_format_stats("total(H)", total_stats))
    if validate_parse_fail:
        print("validate parse failures:", validate_parse_fail)

    if total_stats:
        print("\nSuggested H for modeling:")
        print("H_avg =", f"{total_stats['avg']:.3f}s")
        print("H_median =", f"{total_stats['median']:.3f}s")
        print("H_p90 =", f"{total_stats['p90']:.3f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
