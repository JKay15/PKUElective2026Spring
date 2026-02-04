#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import time

from autoelective.config import AutoElectiveConfig
from autoelective.iaaa import IAAAClient
from autoelective.elective import ElectiveClient
from autoelective.parser import get_sida
from autoelective.exceptions import ElectiveException


def login_elective(cfg):
    iaaa = IAAAClient(timeout=cfg.iaaa_client_timeout)
    elect = ElectiveClient(id=0, timeout=cfg.elective_client_timeout)

    iaaa.oauth_home()
    r = iaaa.oauth_login(cfg.iaaa_id, cfg.iaaa_password)
    token = r.json()["token"]

    r = elect.sso_login(token)
    if cfg.is_dual_degree:
        sida = get_sida(r)
        elect.sso_login_dual_degree(sida, cfg.identity, r.url)

    return elect


def main():
    parser = argparse.ArgumentParser(description="Fetch captcha samples from PKU elective")
    parser.add_argument("--count", type=int, default=10, help="number of captchas to fetch")
    parser.add_argument("--sleep", type=float, default=0.5, help="sleep seconds between requests")
    parser.add_argument("--out", default="cache/captcha_samples", help="output directory")
    args = parser.parse_args()

    cfg = AutoElectiveConfig()
    os.makedirs(args.out, exist_ok=True)

    elect = login_elective(cfg)

    ok = 0
    for i in range(args.count):
        try:
            r = elect.get_DrawServlet()
            ts = int(time.time() * 1000)
            path = os.path.join(args.out, f"captcha_{ts}_{i}.jpg")
            with open(path, "wb") as f:
                f.write(r.content)
            ok += 1
        except ElectiveException as e:
            print("Elective error:", e)
            break
        except Exception as e:
            print("Unexpected error:", e)
            break
        time.sleep(args.sleep)

    print(f"Saved {ok} captcha images to {args.out}")


if __name__ == "__main__":
    main()
