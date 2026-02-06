#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
List electSupplement hrefs from a SupplyCancel HTML fixture.

Default: offline/print-only (no network).
Optional: --fetch + --confirm-elect to actually call electSupplement.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_fixture(path: str) -> bytes:
    with open(path, "rb") as fp:
        return fp.read()


def _parse_hrefs(html_bytes: bytes):
    from autoelective.parser import get_tree, get_tables, get_courses_with_detail

    tree = get_tree(html_bytes)
    tables = get_tables(tree)
    if len(tables) < 1:
        return []
    try:
        courses = get_courses_with_detail(tables[0])
    except Exception:
        courses = []
    hrefs = []
    for c in courses:
        if getattr(c, "href", None):
            hrefs.append((c, c.href))
    return hrefs


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="List electSupplement hrefs from fixture.")
    parser.add_argument("--fixture", required=True, help="path to supplycancel html fixture")
    parser.add_argument("--limit", type=int, default=20, help="max hrefs to show/fetch")
    parser.add_argument("--fetch", action="store_true", help="actually call electSupplement (DANGEROUS)")
    parser.add_argument("--confirm-elect", action="store_true", help="required to allow --fetch")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between fetches")
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="config.ini path (required for --fetch). If set, overrides AUTOELECTIVE_CONFIG_INI.",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.fixture):
        print("[ERROR] fixture not found:", args.fixture)
        return 2

    raw = _load_fixture(args.fixture)
    hrefs = _parse_hrefs(raw)
    if not hrefs:
        print("[WARN] no electSupplement hrefs found in fixture")
        return 0

    limit = max(1, int(args.limit))
    hrefs = hrefs[:limit]

    print("Found %d hrefs (showing %d):" % (len(hrefs), len(hrefs)))
    for c, href in hrefs:
        print("-", c, "->", href)

    if not args.fetch:
        return 0

    if not args.confirm_elect:
        print("[ERROR] --fetch requires --confirm-elect (dangerous: may submit elections).")
        return 3

    if not args.config:
        print("[ERROR] --fetch requires -c/--config")
        return 3

    from autoelective.environ import Environ
    Environ().config_ini = args.config
    from autoelective.config import AutoElectiveConfig
    from autoelective.exceptions import ElectiveException

    cfg = AutoElectiveConfig()
    elect = _login(cfg)

    for c, href in hrefs:
        try:
            print("[FETCH] electSupplement:", c)
            r = elect.get_ElectSupplement(href)
            print("  -> status:", getattr(r, "status_code", "?"), "url:", getattr(r, "url", ""))
        except ElectiveException as e:
            print("  -> ElectiveException:", e)
        except Exception as e:
            print("  -> Error:", e)
        if args.sleep:
            time.sleep(max(0.0, float(args.sleep)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
