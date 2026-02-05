#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Promote sanitized live fixtures (captured under cache/) into stable, versioned test fixtures.

This script is designed for the Phase 1 runbook:
- src defaults to cache/live_fixtures/sanitized (git-ignored)
- dst defaults to tests/fixtures/2026_phase1 (tracked)
- for each fixture name, pick the latest capture by meta.ts
- copy to stable filenames like helpcontroller.html, supplycancel.html, supplement_p2.html
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Dict, List, Tuple


def _iter_meta_files(src_dir: str) -> List[str]:
    if not os.path.isdir(src_dir):
        return []
    out = []
    for name in os.listdir(src_dir):
        if name.endswith(".meta.json"):
            out.append(os.path.join(src_dir, name))
    return sorted(out)


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _pick_latest_by_name(src_dir: str) -> Dict[str, Dict]:
    """
    Return mapping: fixture_name -> meta dict (latest ts wins).
    """
    latest = {}
    for meta_path in _iter_meta_files(src_dir):
        try:
            meta = _load_json(meta_path)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        name = (meta.get("name") or "").strip()
        ts = (meta.get("ts") or "").strip()
        rel = (meta.get("path") or "").strip()
        if not name or not ts or not rel:
            continue
        content_path = os.path.join(src_dir, rel)
        if not os.path.isfile(content_path):
            continue
        cur = latest.get(name)
        if cur is None or ts > (cur.get("ts") or ""):
            meta2 = dict(meta)
            meta2["_meta_path"] = meta_path
            meta2["_content_path"] = content_path
            latest[name] = meta2
    return latest


def _copy_file(src: str, dst: str, force: bool) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        if not force:
            raise FileExistsError(dst)
        os.remove(dst)
    shutil.copy2(src, dst)


def _stable_name(name: str, src_content_path: str) -> str:
    _, ext = os.path.splitext(src_content_path)
    ext = ext.lstrip(".") or "bin"
    return f"{name}.{ext}"


def _write_manifest(dst_dir: str, manifest: dict) -> None:
    os.makedirs(dst_dir, exist_ok=True)
    path = os.path.join(dst_dir, "MANIFEST.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Promote sanitized live fixtures into tests/fixtures.")
    parser.add_argument("--src", default="cache/live_fixtures/sanitized", help="source directory (default: cache/live_fixtures/sanitized)")
    parser.add_argument("--dst", default="tests/fixtures/2026_phase1", help="destination directory (default: tests/fixtures/2026_phase1)")
    parser.add_argument(
        "--names",
        default="helpcontroller,supplycancel,supplement_p2",
        help="comma-separated fixture names to promote (default: helpcontroller,supplycancel,supplement_p2)",
    )
    parser.add_argument("--strict", action="store_true", help="fail if any requested name is missing")
    parser.add_argument("--force", action="store_true", help="overwrite existing promoted fixtures")
    parser.add_argument("--dry-run", action="store_true", help="print what would be copied without writing")
    args = parser.parse_args(argv)

    src_dir = args.src
    dst_dir = args.dst
    want = [n.strip() for n in (args.names or "").split(",") if n.strip()]
    if not want:
        print("[ERROR] no --names specified")
        return 2

    latest = _pick_latest_by_name(src_dir)
    missing = [n for n in want if n not in latest]
    if missing:
        msg = "[ERROR] missing fixtures in src: " + ", ".join(missing)
        if args.strict:
            print(msg)
            return 3
        print(msg)

    promoted: List[Tuple[str, str, str]] = []
    for name in want:
        meta = latest.get(name)
        if not meta:
            continue
        src_content = meta["_content_path"]
        src_meta = meta["_meta_path"]
        dst_content = os.path.join(dst_dir, _stable_name(name, src_content))
        dst_meta = os.path.join(dst_dir, f"{name}.meta.json")
        promoted.append((src_content, dst_content, meta.get("ts") or ""))
        if args.dry_run:
            print("[DRY] copy", src_content, "->", dst_content)
            print("[DRY] copy", src_meta, "->", dst_meta)
            continue
        _copy_file(src_content, dst_content, force=args.force)
        _copy_file(src_meta, dst_meta, force=args.force)

    manifest = {
        "src": os.path.abspath(src_dir),
        "dst": os.path.abspath(dst_dir),
        "requested": want,
        "promoted": [
            {
                "name": os.path.splitext(os.path.basename(dst))[0],
                "ts": ts,
                "from": os.path.relpath(src, start=src_dir),
                "to": os.path.basename(dst),
            }
            for src, dst, ts in promoted
        ],
    }
    if not args.dry_run:
        _write_manifest(dst_dir, manifest)

    print("Promoted %d fixture(s) into %s" % (len(promoted), dst_dir))
    if missing:
        print("Missing:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
