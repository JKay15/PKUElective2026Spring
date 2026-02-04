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


def parse_label_from_filename(path):
    name = os.path.basename(path)
    stem, _ = os.path.splitext(name)
    if "_" not in stem:
        return None
    # take last underscore segment as label
    label = stem.split("_")[-1]
    return label or None


def normalize(text):
    if text is None:
        return ""
    # keep alnum only, uppercase
    return "".join(ch for ch in text if ch.isalnum()).upper()


def char_accuracy(gt, pred):
    gt = normalize(gt)
    pred = normalize(pred)
    if not gt and not pred:
        return 1.0
    if not gt:
        return 0.0
    # align by position; penalize length mismatch
    max_len = max(len(gt), len(pred))
    if max_len == 0:
        return 1.0
    correct = 0
    for i in range(max_len):
        g = gt[i] if i < len(gt) else None
        p = pred[i] if i < len(pred) else None
        if g is not None and p is not None and g == p:
            correct += 1
    return correct / max_len


def main():
    parser = argparse.ArgumentParser(description="Benchmark Baidu OCR speed/accuracy on a folder of captcha images")
    parser.add_argument("--images-dir", required=True, help="folder with captcha images")
    parser.add_argument("--max", type=int, default=None, help="max images to test")
    parser.add_argument("--sleep", type=float, default=0.1, help="sleep between requests")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--labels-from-filename", action="store_true", default=True)
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
        exact_hits = 0
        char_scores = []
        labeled = 0

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
                    pred = words[0]["words"] if words else ""
                    results.append((os.path.basename(path), words))
                    if args.labels_from_filename:
                        gt = parse_label_from_filename(path)
                        if gt:
                            labeled += 1
                            if normalize(pred) == normalize(gt):
                                exact_hits += 1
                            char_scores.append(char_accuracy(gt, pred))
            except Exception:
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

        if labeled > 0:
            exact_rate = exact_hits / labeled
            char_rate = statistics.mean(char_scores) if char_scores else 0.0
            print(f"accuracy: exact={exact_rate:.3f} char={char_rate:.3f} (labeled={labeled})")
        else:
            print("accuracy: n/a (no labels)")

        # show a few sample results
        for name, words in results[:5]:
            print("-", name, "->", words)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
