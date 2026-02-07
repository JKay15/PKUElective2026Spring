#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Static audit tool: compare baseline commit vs current workspace to extract
"request-footprint / stability relevant" behaviors and highlight deltas/conflicts.

Outputs:
- JSON report (default: cache/audit/baseline_footprint_audit.json)
- Markdown summary to stdout (for pasting into BASELINE_FOOTPRINT_AUDIT.md)

This script is intentionally dependency-free (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASELINE = "baseline-footprint"
DEFAULT_OUT = os.path.join(REPO_ROOT, "cache", "audit", "baseline_footprint_audit.json")


def _run_git(args: List[str]) -> str:
    out = subprocess.check_output(
        ["git"] + args,
        cwd=REPO_ROOT,
        stderr=subprocess.STDOUT,
    )
    return out.decode("utf-8", errors="replace")


def _git_ls_tree_py(commit: str, prefix: str) -> List[str]:
    out = _run_git(["ls-tree", "-r", "--name-only", commit, prefix])
    paths = []
    for line in out.splitlines():
        p = line.strip()
        if not p:
            continue
        if p.endswith(".py"):
            paths.append(p)
    return paths


def _git_show_text(commit: str, path: str) -> Optional[str]:
    try:
        return _run_git(["show", "%s:%s" % (commit, path)])
    except subprocess.CalledProcessError:
        return None


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read()
    except Exception:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                return fp.read()
        except Exception:
            return None


def _walk_py(prefix_dir: str) -> List[str]:
    out = []
    base = os.path.join(REPO_ROOT, prefix_dir)
    for root, _dirs, files in os.walk(base):
        for name in files:
            if not name.endswith(".py"):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, REPO_ROOT)
            out.append(rel)
    return sorted(out)


def _find_evidence_lines(content: str, regex: re.Pattern, limit_total: int = 20) -> List[dict]:
    if not content:
        return []
    lines = content.splitlines()
    out = []
    for i, line in enumerate(lines, start=1):
        if regex.search(line):
            out.append({"line": i, "text": line.strip()})
            if len(out) >= limit_total:
                break
    return out


def _extract_header_writes(content: str) -> List[str]:
    if not content:
        return []
    rx = re.compile(r"""headers\s*\[\s*["']([^"']+)["']\s*\]\s*=""")
    return sorted(set(m.group(1) for m in rx.finditer(content)))


def _extract_default_headers_keys(content: str, class_name: str) -> List[str]:
    """
    Best-effort extraction of `default_headers = {...}` keys inside a class block.
    """
    if not content:
        return []
    # Locate class block start.
    mat = re.search(r"\bclass\s+%s\b" % re.escape(class_name), content)
    if not mat:
        return []
    start = mat.start()
    # Search forward for default_headers.
    m2 = re.search(r"default_headers\s*=\s*{", content[start:])
    if not m2:
        return []
    pos = start + m2.end()  # position after "{"
    # Scan until matching "}" (shallow, dict literal should not contain nested braces).
    end = content.find("}", pos)
    if end == -1:
        return []
    body = content[pos:end]
    # keys: "Key": ... or 'Key': ...
    key_rx = re.compile(r"""["']([^"']+)["']\s*:""")
    keys = sorted(set(m.group(1) for m in key_rx.finditer(body)))
    return keys


def _count_calls(content: str, needle: str) -> int:
    if not content:
        return 0
    return content.count(needle)


def _scan_feature(
    code_by_path: Dict[str, str],
    patterns: List[Tuple[str, re.Pattern]],
    limit_per_file: int = 3,
    limit_total: int = 30,
) -> Tuple[bool, List[dict]]:
    evidence = []
    for path, content in sorted(code_by_path.items()):
        if not content:
            continue
        for _label, rx in patterns:
            hits = _find_evidence_lines(content, rx, limit_total=limit_per_file)
            for h in hits:
                evidence.append({"file": path, "line": h["line"], "text": h["text"]})
                if len(evidence) >= limit_total:
                    return True, evidence
    return (len(evidence) > 0), evidence


def _build_items(baseline: Dict[str, str], current: Dict[str, str]) -> List[dict]:
    items = []

    def add_item(
        item_id: str,
        category: str,
        desc: str,
        base_patterns: List[Tuple[str, re.Pattern]],
        cur_patterns: List[Tuple[str, re.Pattern]],
        risk: str = "",
    ) -> None:
        b_present, b_ev = _scan_feature(baseline, base_patterns)
        c_present, c_ev = _scan_feature(current, cur_patterns)
        if b_present and c_present:
            status = "inherited"
        elif b_present and not c_present:
            status = "missing"
        elif (not b_present) and c_present:
            status = "added"
        else:
            status = "absent"
        items.append(
            {
                "id": item_id,
                "category": category,
                "desc": desc,
                "risk": risk,
                "baseline": {"present": b_present, "evidence": b_ev},
                "current": {"present": c_present, "evidence": c_ev},
                "status": status,
            }
        )

    add_item(
        "FP-UA-LOGIN",
        "fingerprint",
        "Login/session sets User-Agent via random.choice(USER_AGENT_LIST), reused per session",
        base_patterns=[
            ("ua", re.compile(r"random\.choice\(\s*USER_AGENT_LIST\s*\)")),
            ("set", re.compile(r"\.set_user_agent\(")),
        ],
        cur_patterns=[
            ("ua", re.compile(r"random\.choice\(\s*USER_AGENT_LIST\s*\)")),
            ("set", re.compile(r"\.set_user_agent\(")),
        ],
        risk="UA changing too frequently may look suspicious; keep baseline 'per session' behavior.",
    )

    add_item(
        "FP-COOKIE-SSO",
        "fingerprint",
        "SSO login sends dummy JSESSIONID Cookie to avoid StatusCode 101",
        base_patterns=[
            ("jsession", re.compile(r"JSESSIONID=.*!")),
            ("cookie", re.compile(r"headers\\[\"Cookie\"\\]\s*=\s*dummy_cookie")),
        ],
        cur_patterns=[
            ("jsession", re.compile(r"JSESSIONID=.*!")),
            ("cookie", re.compile(r"headers\\[\"Cookie\"\\]\s*=\s*dummy_cookie")),
        ],
        risk="Removing this may break login or change server expectations.",
    )

    add_item(
        "FP-REF-ACT",
        "fingerprint",
        "Referer strategy for SupplyCancel/Draw/Validate/ElectSupplement",
        base_patterns=[
            ("referer", re.compile(r"headers\\[\"Referer\"\\]")),
            ("supplycancel", re.compile(r"ElectiveURL\.SupplyCancel")),
            ("help", re.compile(r"ElectiveURL\.HelpController")),
        ],
        cur_patterns=[
            ("referer", re.compile(r"headers\\[\"Referer\"\\]")),
            ("supplycancel", re.compile(r"ElectiveURL\.SupplyCancel")),
            ("help", re.compile(r"ElectiveURL\.HelpController")),
        ],
        risk="Unexpected/missing Referer may trigger system prompt warnings.",
    )

    add_item(
        "FREQ-JITTER",
        "frequency",
        "Refresh jitter via random deviation around refresh_interval",
        base_patterns=[
            ("fn", re.compile(r"def\s+_get_refresh_interval\(")),
            ("rand", re.compile(r"random\.random\(")),
            ("dev", re.compile(r"refresh_random_deviation")),
        ],
        cur_patterns=[
            ("fn", re.compile(r"def\s+_get_refresh_interval\(")),
            ("rand", re.compile(r"random\.random\(")),
            ("dev", re.compile(r"refresh_random_deviation")),
        ],
        risk="Fixed-period refresh is more bot-like; jitter reduces periodicity.",
    )

    add_item(
        "REQ-MIN-FOOTPRINT",
        "request_footprint",
        "No-availability rounds primarily refresh list pages; captcha endpoints only when needed",
        base_patterns=[
            ("supply", re.compile(r"get_SupplyCancel")),
            ("draw", re.compile(r"get_DrawServlet")),
            ("validate", re.compile(r"get_Validate")),
            ("elect", re.compile(r"get_ElectSupplement")),
        ],
        cur_patterns=[
            ("supply", re.compile(r"get_SupplyCancel")),
            ("draw", re.compile(r"get_DrawServlet")),
            ("validate", re.compile(r"get_Validate")),
            ("elect", re.compile(r"get_ElectSupplement")),
            ("probe", re.compile(r"_run_captcha_probe_loop")),
        ],
        risk="Background captcha probe (if enabled) increases request footprint; must be OFF by default and budgeted.",
    )

    add_item(
        "SESS-PERSIST-COOKIES",
        "session",
        "Persist cookies even when hooks raise (manual extract_cookies_to_jar in persist_cookies)",
        base_patterns=[("persist", re.compile(r"persist_cookies\("))],
        cur_patterns=[("persist", re.compile(r"persist_cookies\("))],
        risk="Without this, session may expire faster due to missed Set-Cookie updates on system pages.",
    )

    add_item(
        "DBG-DUMP",
        "logging",
        "debug_dump_request pickle dumps responses into log/request (risk of tokens/cookies if enabled)",
        base_patterns=[("dump", re.compile(r"def\s+debug_dump_request\("))],
        cur_patterns=[("dump", re.compile(r"def\s+debug_dump_request\("))],
        risk="Must stay OFF by default; dumps must remain under gitignored log/.",
    )

    add_item(
        "NEW-RATE-LIMIT",
        "added_feature",
        "Token-bucket rate limiter (global + per-host) invoked by BaseClient._request",
        base_patterns=[("none", re.compile(r"rate_limit\.throttle"))],
        cur_patterns=[("throttle", re.compile(r"rate_limit\.throttle"))],
        risk="If enabled/misconfigured, may slow burst path; keep default OFF and add integration test.",
    )

    add_item(
        "NEW-PROBE-THREAD",
        "added_feature",
        "Optional captcha probe thread (background Draw+Validate sampling)",
        base_patterns=[("none", re.compile(r"_run_captcha_probe_loop"))],
        cur_patterns=[("probe", re.compile(r"_run_captcha_probe_loop"))],
        risk="Can add background captcha traffic; must be OFF by default; prefer shared pool.",
    )

    add_item(
        "NEW-OFFLINE-CB",
        "added_feature",
        "OFFLINE circuit breaker + observation window",
        base_patterns=[("none", re.compile(r"OFFLINE_ENABLED"))],
        cur_patterns=[("offline", re.compile(r"OFFLINE_ENABLED"))],
        risk="Should reduce traffic during network failures (more conservative).",
    )

    add_item(
        "NEW-NOT-IN-OP-BACKOFF",
        "added_feature",
        "Not-in-operation dynamic backoff based on HelpController schedule (TTL cached)",
        base_patterns=[("none", re.compile(r"_update_not_in_operation_backoff"))],
        cur_patterns=[("backoff", re.compile(r"_update_not_in_operation_backoff"))],
        risk="Should reduce traffic when not in operation time (more conservative).",
    )

    return items


def _mk_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _load_code_baseline(commit: str) -> Dict[str, str]:
    files = _git_ls_tree_py(commit, "autoelective")
    code = {}
    for p in files:
        text = _git_show_text(commit, p)
        if text is None:
            continue
        code[p] = text
    return code


def _load_code_current() -> Dict[str, str]:
    files = _walk_py("autoelective")
    code = {}
    for rel in files:
        text = _read_text(os.path.join(REPO_ROOT, rel))
        if text is None:
            continue
        code[rel] = text
    return code


def _extract_fingerprint_snapshot(code_by_path: Dict[str, str]) -> dict:
    iaaa_py = code_by_path.get("autoelective/iaaa.py", "")
    elective_py = code_by_path.get("autoelective/elective.py", "")

    iaaa_keys = _extract_default_headers_keys(iaaa_py, "IAAAClient")
    elective_keys = _extract_default_headers_keys(elective_py, "ElectiveClient")

    header_writes = {}
    for p, content in code_by_path.items():
        keys = _extract_header_writes(content)
        if keys:
            header_writes[p] = keys

    return {
        "default_headers": {
            "IAAAClient": iaaa_keys,
            "ElectiveClient": elective_keys,
        },
        "header_writes": header_writes,
        "counts": {
            "random_choice_user_agent_list": sum(
                _count_calls(c, "random.choice(USER_AGENT_LIST)") for c in code_by_path.values()
            ),
            "time_sleep": sum(_count_calls(c, "time.sleep(") for c in code_by_path.values()),
        },
    }


def _diff_sets(a: List[str], b: List[str]) -> dict:
    sa = set(a or [])
    sb = set(b or [])
    return {
        "only_in_baseline": sorted(sa - sb),
        "only_in_current": sorted(sb - sa),
        "common": sorted(sa & sb),
    }


def _render_markdown(items: List[dict], fp_base: dict, fp_cur: dict, baseline_commit: str) -> str:
    lines = []
    lines.append("# Baseline Request Footprint / Stability Audit Summary")
    lines.append("")
    lines.append("- baseline_commit: `%s`" % baseline_commit)
    lines.append("- generated_at_utc: `%s`" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    lines.append("")

    # Fingerprint headers diff
    lines.append("## Fingerprint: default_headers diff")
    for clz in ("IAAAClient", "ElectiveClient"):
        d = _diff_sets(fp_base.get("default_headers", {}).get(clz, []), fp_cur.get("default_headers", {}).get(clz, []))
        lines.append("")
        lines.append("### %s" % clz)
        lines.append("- only_in_baseline: `%s`" % (", ".join(d["only_in_baseline"]) or ""))
        lines.append("- only_in_current: `%s`" % (", ".join(d["only_in_current"]) or ""))

    # Items table
    lines.append("")
    lines.append("## Feature Items")
    lines.append("")
    lines.append("| id | category | status | baseline | current | risk |")
    lines.append("|---|---|---|---:|---:|---|")
    for it in items:
        lines.append(
            "| `{id}` | {cat} | **{st}** | {bp} | {cp} | {risk} |".format(
                id=it["id"],
                cat=it["category"],
                st=it["status"],
                bp="yes" if it["baseline"]["present"] else "no",
                cp="yes" if it["current"]["present"] else "no",
                risk=(it.get("risk") or "").replace("|", "\\|"),
            )
        )

    # Missing/Added lists
    missing = [it for it in items if it["status"] == "missing"]
    added = [it for it in items if it["status"] == "added"]
    if missing:
        lines.append("")
        lines.append("## Missing Baseline Behaviors (P0)")
        for it in missing:
            lines.append("- `%s`: %s" % (it["id"], it["desc"]))
    if added:
        lines.append("")
        lines.append("## Added Behaviors (Review for conflicts)")
        for it in added:
            lines.append("- `%s`: %s" % (it["id"], it["desc"]))

    return "\n".join(lines) + "\n"


def generate_audit(baseline_commit: str) -> dict:
    base_code = _load_code_baseline(baseline_commit)
    cur_code = _load_code_current()

    items = _build_items(base_code, cur_code)
    fp_base = _extract_fingerprint_snapshot(base_code)
    fp_cur = _extract_fingerprint_snapshot(cur_code)

    report = {
        "baseline_commit": baseline_commit,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": items,
        "fingerprint": {
            "baseline": fp_base,
            "current": fp_cur,
            "default_headers_diff": {
                "IAAAClient": _diff_sets(
                    fp_base.get("default_headers", {}).get("IAAAClient", []),
                    fp_cur.get("default_headers", {}).get("IAAAClient", []),
                ),
                "ElectiveClient": _diff_sets(
                    fp_base.get("default_headers", {}).get("ElectiveClient", []),
                    fp_cur.get("default_headers", {}).get("ElectiveClient", []),
                ),
            },
        },
    }
    report["markdown_summary"] = _render_markdown(items, fp_base, fp_cur, baseline_commit)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit baseline request-footprint/stability behaviors vs current workspace"
    )
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE,
        help="baseline git commit/tag (default: baseline-footprint)",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="output json path (default: cache/audit/baseline_footprint_audit.json)",
    )
    args = parser.parse_args(argv)

    report = generate_audit(args.baseline)

    out_path = os.path.abspath(args.out)
    _mk_dir(out_path)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    sys.stdout.write(report.get("markdown_summary", ""))
    sys.stdout.write("\nSaved JSON to: %s\n" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
