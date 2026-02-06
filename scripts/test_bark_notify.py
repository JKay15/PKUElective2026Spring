#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Send a Bark test notification using config.ini / config.phase1.ini.
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test Bark notification with config token.")
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="config.ini path (optional). If set, overrides AUTOELECTIVE_CONFIG_INI.",
    )
    args = parser.parse_args(argv)

    if args.config:
        from autoelective.environ import Environ

        Environ().config_ini = args.config

    from autoelective.config import AutoElectiveConfig
    from autoelective.notification.bark_push import test_notify

    cfg = AutoElectiveConfig()
    token = cfg.wechat_token
    if not token:
        print("[ERROR] notification.token is empty in config")
        return 2

    test_notify(token)
    print("Sent Bark test notification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
