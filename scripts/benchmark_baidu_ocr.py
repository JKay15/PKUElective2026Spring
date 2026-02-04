#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import os
import statistics
import time
from configparser import RawConfigParser

import requests


def load_keys():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(repo_root, "config.ini")
    parser = RawConfigParser()
    parser.read(config_path, encoding="utf-8-sig")

    api_key = None
    secret_key = None
    if parser.has_section("captcha"):
        api_key = parser.get("captcha", "baidu_api_key", fallback=None)
        secret_key = parser.get("captcha", "baidu_secret_key", fallback=None)

    api_key = api_key or os.getenv("BAIDU_OCR_API_KEY")
    secret_key = secret_key or os.getenv("BAIDU_OCR_SECRET_KEY")
    return api_key, secret_key


def get_token(api_key, secret_key, timeout=10):
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key,
    }
    resp = requests.post(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"token error: {data}")
    return data["access_token"]


def list_images(images_dir, max_images=None):
    exts = {".png", ".jpg", ".jpeg", ".bmp"}
    files = []
    for name in sorted(os.listdir(images_dir)):
        path = os.path.join(images_dir, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in exts:
            files.append(path)
    if max_images:
        files = files[:max_images]
    return files


def call_ocr(token, mode, image_bytes, timeout=10):
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/{mode}?access_token={token}"
    payload = {
        "image": base64.b64encode(image_bytes).decode("utf-8"),
        "detect_direction": "true",
        "paragraph": "false",
        "probability": "false",
        "multidirectional_recognize": "true",
    }
    t0 = time.time()
    resp = requests.post(url, data=payload, timeout=timeout)
    dt = time.time() - t0
    resp.raise_for_status()
    data = resp.json()
    return dt, data


def summarize(latencies):
    if not latencies:
        return {}
    return {
        "count": len(latencies),
        "avg": statistics.mean(latencies),
        "median": statistics.median(latencies),
        "p90": statistics.quantiles(latencies, n=10)[8] if len(latencies) >= 10 else max(latencies),
        "min": min(latencies),
        "max": max(latencies),
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Baidu OCR speed on a folder of captcha images")
    parser.add_argument("--images-dir", required=True, help="folder with captcha images")
    parser.add_argument("--max", type=int, default=None, help="max images to test")
    parser.add_argument("--sleep", type=float, default=0.1, help="sleep between requests")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    api_key, secret_key = load_keys()
    if not api_key or not secret_key:
        print("Baidu OCR keys not found in config.ini or environment.")
        return 2

    images = list_images(args.images_dir, args.max)
    if not images:
        print("No images found.")
        return 3

    modes = ["general_basic", "accurate_basic"]

    for mode in modes:
        token = get_token(api_key, secret_key, timeout=args.timeout)
        ok = 0
        fail = 0
        latencies = []
        results = []
        for path in images:
            with open(path, "rb") as f:
                img = f.read()
            try:
                dt, data = call_ocr(token, mode, img, timeout=args.timeout)
                if "error_code" in data:
                    fail += 1
                else:
                    ok += 1
                    latencies.append(dt)
                    words = data.get("words_result", [])
                    results.append((os.path.basename(path), words))
            except Exception as e:
                fail += 1
            time.sleep(args.sleep)

        stats = summarize(latencies)
        print("\n=== MODE:", mode, "===")
        print("ok:", ok, "fail:", fail)
        if stats:
            print(
                "latency(s): avg={avg:.3f} median={median:.3f} p90={p90:.3f} min={min:.3f} max={max:.3f}".format(
                    **stats
                )
            )
        else:
            print("latency(s): n/a")

        # show a few sample results
        for name, words in results[:5]:
            print("-", name, "->", words)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
