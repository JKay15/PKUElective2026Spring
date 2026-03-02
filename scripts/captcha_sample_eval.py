#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from autoelective.config import AutoElectiveConfig
from autoelective.captcha import get_recognizer
from autoelective.captcha.targets import (
    default_targets_from_config,
    format_target,
    parse_targets_csv,
)


def _load_labels(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("labels must be a json object: {sample_id: label}")
    return {str(k): str(v) for k, v in data.items()}


def _iter_samples(sample_dir):
    if not os.path.isdir(sample_dir):
        return []
    files = os.listdir(sample_dir)
    metas = {f[:-5]: f for f in files if f.endswith(".json")}
    samples = []
    for f in files:
        if f.endswith(".json"):
            continue
        base = os.path.splitext(f)[0]
        meta_file = metas.get(base)
        meta = None
        if meta_file:
            try:
                with open(os.path.join(sample_dir, meta_file), "r", encoding="utf-8") as fp:
                    meta = json.load(fp)
            except Exception:
                meta = None
        samples.append((base, os.path.join(sample_dir, f), meta))
    return samples


def _calc_char_stats(label, pred):
    if label is None:
        return 0, 0
    label = str(label)
    pred = "" if pred is None else str(pred)
    if not label and not pred:
        return 0, 0
    n = max(len(label), len(pred), 1)
    m = min(len(label), len(pred))
    match = 0
    for i in range(m):
        if label[i] == pred[i]:
            match += 1
    return match, n


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[max(0, min(k, len(values) - 1))]


def _format_ms(x):
    if x is None:
        return "--"
    return "%.1f" % x


def main():
    parser = argparse.ArgumentParser(description="Evaluate captcha recognizers on sampled images")
    parser.add_argument("--sample-dir", default=None, help="sample directory")
    parser.add_argument("--labels", default=None, help="path to labels json: {sample_id: label}")
    parser.add_argument(
        "--targets",
        default=None,
        help="comma-separated targets: provider[:model],provider[:model] (default: config provider + fallback)",
    )
    parser.add_argument("--limit", type=int, default=0, help="limit number of samples")
    parser.add_argument("--shuffle", action="store_true", help="shuffle samples")
    args = parser.parse_args()

    config = AutoElectiveConfig()
    sample_dir = args.sample_dir or config.captcha_sample_dir
    labels = _load_labels(args.labels)

    try:
        if args.targets:
            targets = parse_targets_csv(args.targets)
        else:
            targets = default_targets_from_config(config)
    except ValueError as e:
        print("[ERROR] invalid targets:", e)
        return 2

    samples = _iter_samples(sample_dir)
    if args.shuffle:
        import random
        random.shuffle(samples)
    if args.limit and args.limit > 0:
        samples = samples[: args.limit]

    if not samples:
        print("No samples found in %s" % sample_dir)
        return 1

    recognizers = {}
    for provider, model_name in targets:
        target_name = format_target(provider, model_name)
        recognizers[target_name] = get_recognizer(provider, model_name=model_name)

    results = {}
    for target_name in recognizers:
        results[target_name] = {
            "attempts": 0,
            "errors": 0,
            "labeled": 0,
            "exact": 0,
            "char_match": 0,
            "char_total": 0,
            "latencies": [],
        }

    for base, path, meta in samples:
        try:
            with open(path, "rb") as fp:
                raw = fp.read()
        except Exception:
            continue
        label = labels.get(base)
        if label is None and isinstance(meta, dict):
            label = meta.get("label") or meta.get("code")
        for p, recog in recognizers.items():
            st = results[p]
            st["attempts"] += 1
            t0 = time.time()
            try:
                cap = recog.recognize(raw)
                pred = cap.code if hasattr(cap, "code") else str(cap)
                dt = (time.time() - t0) * 1000.0
                st["latencies"].append(dt)
                if label is not None:
                    st["labeled"] += 1
                    if str(label) == str(pred):
                        st["exact"] += 1
                    m, n = _calc_char_stats(label, pred)
                    st["char_match"] += m
                    st["char_total"] += n
            except Exception:
                st["errors"] += 1

    print("Sample dir: %s" % sample_dir)
    print("Targets: %s" % ", ".join(recognizers.keys()))
    print("Samples: %d" % len(samples))
    print("")

    for target_name in recognizers:
        st = results[target_name]
        lat = st["latencies"]
        exact = st["exact"]
        labeled = st["labeled"]
        exact_rate = (exact / labeled) if labeled else None
        char_rate = (st["char_match"] / st["char_total"]) if st["char_total"] else None
        print("== %s ==" % target_name)
        print("attempts=%d errors=%d labeled=%d" % (st["attempts"], st["errors"], labeled))
        if labeled:
            print("exact=%.3f char=%.3f" % (exact_rate, char_rate))
        else:
            print("exact=-- char=-- (no labels)")
        print(
            "latency_ms: avg=%s p50=%s p90=%s p95=%s p99=%s max=%s"
            % (
                _format_ms(sum(lat) / len(lat) if lat else None),
                _format_ms(_percentile(lat, 50)),
                _format_ms(_percentile(lat, 90)),
                _format_ms(_percentile(lat, 95)),
                _format_ms(_percentile(lat, 99)),
                _format_ms(max(lat) if lat else None),
            )
        )
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
