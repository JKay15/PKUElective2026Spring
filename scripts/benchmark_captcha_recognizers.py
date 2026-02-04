#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import statistics
import time

from autoelective.captcha import get_recognizer
from autoelective.exceptions import OperationFailedError, OperationTimeoutError, RecognizerError


def list_images(images_dir, max_images=None):
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
    files = []
    for name in sorted(os.listdir(images_dir)):
        path = os.path.join(images_dir, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in exts:
            files.append(path)
    if max_images:
        files = files[:max_images]
    return files


def parse_label_from_filename(path):
    name = os.path.basename(path)
    stem, _ = os.path.splitext(name)
    if "_" not in stem:
        return None
    return stem.split("_")[-1] or None


def normalize(text):
    if text is None:
        return ""
    return "".join(ch for ch in str(text) if ch.isalnum()).upper()


def char_accuracy(gt, pred):
    gt = normalize(gt)
    pred = normalize(pred)
    if not gt and not pred:
        return 1.0
    if not gt:
        return 0.0
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


def main():
    parser = argparse.ArgumentParser(description="Benchmark captcha recognizers (speed + accuracy)")
    parser.add_argument("--images-dir", required=True, help="folder with captcha images")
    parser.add_argument("--providers", required=True, help="comma-separated recognizer names, e.g. baidu,gemini")
    parser.add_argument("--max", type=int, default=None, help="max images to test")
    parser.add_argument("--sleep", type=float, default=0.05, help="sleep between requests")
    args = parser.parse_args()

    images = list_images(args.images_dir, args.max)
    if not images:
        print("No images found.")
        return 2

    providers = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    if not providers:
        print("No providers specified.")
        return 3

    for provider in providers:
        recognizer = get_recognizer(provider)
        ok = 0
        fail = 0
        latencies = []
        exact_hits = 0
        char_scores = []
        labeled = 0
        samples = []

        for path in images:
            with open(path, "rb") as f:
                raw = f.read()
            t0 = time.time()
            try:
                cap = recognizer.recognize(raw)
                dt = time.time() - t0
                ok += 1
                latencies.append(dt)
                pred = cap.code
                gt = parse_label_from_filename(path)
                if gt:
                    labeled += 1
                    if normalize(pred) == normalize(gt):
                        exact_hits += 1
                    char_scores.append(char_accuracy(gt, pred))
                if len(samples) < 5:
                    samples.append((os.path.basename(path), gt, pred))
            except (RecognizerError, OperationTimeoutError, OperationFailedError) as e:
                dt = time.time() - t0
                fail += 1
                if len(samples) < 5:
                    samples.append((os.path.basename(path), parse_label_from_filename(path), f"ERROR: {e}"))
            time.sleep(args.sleep)

        stats = summarize(latencies)
        print("\n=== PROVIDER:", provider, "===")
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

        print("samples:")
        for name, gt, pred in samples:
            print("-", name, "gt=", gt, "pred=", pred)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

