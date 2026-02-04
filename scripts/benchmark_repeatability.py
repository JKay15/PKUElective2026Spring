#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import statistics
import sys
import time

# Allow running this file directly.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

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
    parser = argparse.ArgumentParser(
        description="Repeatability benchmark: same image, multiple recognitions."
    )
    parser.add_argument("--images-dir", required=True, help="folder with captcha images")
    parser.add_argument("--providers", required=True, help="comma-separated recognizer names")
    parser.add_argument("--max", type=int, default=20, help="max images to test")
    parser.add_argument("--repeats", type=int, default=5, help="repeats per image")
    parser.add_argument("--sleep", type=float, default=0.05, help="sleep between attempts")
    parser.add_argument("--sleep-image", type=float, default=0.0, help="sleep between images")
    args = parser.parse_args()

    images = list_images(args.images_dir, args.max)
    if not images:
        print("No images found.")
        return 2

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    if not providers:
        print("No providers specified.")
        return 3

    for provider in providers:
        recognizer = get_recognizer(provider)
        latencies = []
        attempt_ok = 0
        attempt_fail = 0

        labeled = 0
        first_exact = []
        best_exact = []
        first_char = []
        best_char = []
        any_success = []
        first_success_attempts = []

        for path in images:
            with open(path, "rb") as f:
                raw = f.read()
            gt = parse_label_from_filename(path)
            if gt:
                labeled += 1

            per_preds = []
            per_chars = []
            per_lat = []
            success_attempt = None

            for i in range(args.repeats):
                t0 = time.time()
                try:
                    cap = recognizer.recognize(raw)
                    dt = time.time() - t0
                    attempt_ok += 1
                    latencies.append(dt)
                    per_lat.append(dt)
                    pred = cap.code
                    per_preds.append(pred)
                    if gt:
                        per_chars.append(char_accuracy(gt, pred))
                    if success_attempt is None:
                        success_attempt = i + 1
                except (RecognizerError, OperationTimeoutError, OperationFailedError):
                    dt = time.time() - t0
                    attempt_fail += 1
                    per_lat.append(dt)
                time.sleep(args.sleep)

            if gt:
                first_pred = per_preds[0] if per_preds else ""
                first_exact.append(normalize(first_pred) == normalize(gt))
                first_char.append(char_accuracy(gt, first_pred))

                best_hit = False
                best_char_score = 0.0
                for pred in per_preds:
                    if normalize(pred) == normalize(gt):
                        best_hit = True
                    best_char_score = max(best_char_score, char_accuracy(gt, pred))
                best_exact.append(best_hit)
                best_char.append(best_char_score)

            any_success.append(success_attempt is not None)
            if success_attempt is not None:
                first_success_attempts.append(success_attempt)

            if args.sleep_image > 0:
                time.sleep(args.sleep_image)

        print("\n=== PROVIDER:", provider, "===")
        print("attempts:", args.repeats * len(images), "ok:", attempt_ok, "fail:", attempt_fail)
        stats = summarize(latencies)
        if stats:
            print(
                "latency(s): avg={avg:.3f} median={median:.3f} p90={p90:.3f} min={min:.3f} max={max:.3f}".format(
                    **stats
                )
            )
        if labeled > 0:
            first_exact_rate = statistics.mean(first_exact) if first_exact else 0.0
            best_exact_rate = statistics.mean(best_exact) if best_exact else 0.0
            first_char_rate = statistics.mean(first_char) if first_char else 0.0
            best_char_rate = statistics.mean(best_char) if best_char else 0.0
            print(
                "accuracy (first): exact={:.3f} char={:.3f} (labeled={})".format(
                    first_exact_rate, first_char_rate, labeled
                )
            )
            print(
                "accuracy (best-of-{}): exact={:.3f} char={:.3f}".format(
                    args.repeats, best_exact_rate, best_char_rate
                )
            )
            print(
                "gain: exact={:+.3f} char={:+.3f}".format(
                    best_exact_rate - first_exact_rate, best_char_rate - first_char_rate
                )
            )
        success_rate = sum(1 for x in any_success if x) / len(any_success)
        print("any-success rate: {:.3f}".format(success_rate))
        if first_success_attempts:
            print(
                "avg attempts to first success: {:.2f}".format(
                    statistics.mean(first_success_attempts)
                )
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

