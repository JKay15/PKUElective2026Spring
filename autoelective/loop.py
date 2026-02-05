#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: loop.py

import os
import time
import random
import threading
import socket
import hashlib
import json as stdjson
import re
from datetime import datetime
from queue import Queue, Empty, Full
from collections import deque, defaultdict
from itertools import combinations
from requests.compat import json
from requests.exceptions import RequestException, Timeout, ConnectionError, SSLError
import numpy as np
from . import __version__, __date__
from .environ import Environ
from .config import AutoElectiveConfig
from .logger import ConsoleLogger, FileLogger
from .course import Course
from .captcha import get_recognizer
from .captcha.adaptive import CaptchaAdaptiveManager
from . import rate_limit
from .parser import get_tables, get_courses, get_courses_with_detail, get_sida
from .hook import _dump_request
from .iaaa import IAAAClient
from .elective import ElectiveClient
from .const import (
    CAPTCHA_CACHE_DIR,
    USER_AGENT_LIST,
    WEB_LOG_DIR,
    WECHAT_MSG,
    WECHAT_PREFIX,
)
from .exceptions import *
from ._internal import mkdir
from .notification.bark_push import Notify

environ = Environ()
config = AutoElectiveConfig()
cout = ConsoleLogger("loop")
ferr = FileLogger("loop.error")  # loop 的子日志，同步输出到 console

username = config.iaaa_id
password = config.iaaa_password
is_dual_degree = config.is_dual_degree
identity = config.identity
refresh_interval = config.refresh_interval
refresh_random_deviation = config.refresh_random_deviation
supply_cancel_page = config.supply_cancel_page
iaaa_client_timeout = config.iaaa_client_timeout
elective_client_timeout = config.elective_client_timeout
login_loop_interval = config.login_loop_interval
elective_client_pool_size = config.elective_client_pool_size
elective_client_max_life = config.elective_client_max_life
is_print_mutex_rules = config.is_print_mutex_rules
REFRESH_BACKOFF_ENABLE = config.refresh_backoff_enable
REFRESH_BACKOFF_FACTOR = config.refresh_backoff_factor
REFRESH_BACKOFF_MAX = config.refresh_backoff_max
REFRESH_BACKOFF_THRESHOLD = config.refresh_backoff_threshold
IAAA_BACKOFF_ENABLE = config.iaaa_backoff_enable
IAAA_BACKOFF_FACTOR = config.iaaa_backoff_factor
IAAA_BACKOFF_MAX = config.iaaa_backoff_max
IAAA_BACKOFF_THRESHOLD = config.iaaa_backoff_threshold
CLIENT_POOL_RESET_THRESHOLD = config.client_pool_reset_threshold
CLIENT_POOL_RESET_COOLDOWN = config.client_pool_reset_cooldown
notify = Notify(
    _disable_push=config.disable_push,
    _token=config.wechat_token,
    _interval_lock=config.minimum_interval,
    _verbosity=config.verbosity,
)

config.check_identify(identity)
config.check_supply_cancel_page(supply_cancel_page)

_USER_WEB_LOG_DIR = os.path.join(WEB_LOG_DIR, config.get_user_subpath())
mkdir(_USER_WEB_LOG_DIR)

# build recognizer chain
_recognizer_names = []
_recognizer_seen = set()
for _name in [config.captcha_provider] + config.captcha_fallback_providers:
    _name = (_name or "").strip().lower()
    if not _name or _name in _recognizer_seen:
        continue
    _recognizer_seen.add(_name)
    _recognizer_names.append(_name)
if not _recognizer_names:
    _recognizer_names = ["baidu"]
_recognizer_map = {n: get_recognizer(n) for n in _recognizer_names}
recognizers = [_recognizer_map[n] for n in _recognizer_names]
recognizer_index = 0
recognizer = recognizers[0]
RECOGNIZER_MAX_ATTEMPT = 15
MIN_REFRESH_INTERVAL = 0.1
CAPTCHA_DEGRADE_FAILURES = config.captcha_degrade_failures
CAPTCHA_DEGRADE_COOLDOWN = config.captcha_degrade_cooldown
CAPTCHA_DEGRADE_MONITOR_ONLY = config.captcha_degrade_monitor_only
CAPTCHA_DEGRADE_NOTIFY = config.captcha_degrade_notify
CAPTCHA_DEGRADE_NOTIFY_INTERVAL = config.captcha_degrade_notify_interval
CAPTCHA_SWITCH_ON_DEGRADE = config.captcha_switch_on_degrade

CAPTCHA_PROBE_ENABLED = config.captcha_probe_enabled
CAPTCHA_PROBE_INTERVAL = config.captcha_probe_interval
CAPTCHA_PROBE_BACKOFF = config.captcha_probe_backoff
CAPTCHA_PROBE_RANDOM_DEV = config.captcha_probe_random_deviation
CAPTCHA_ADAPTIVE_REPORT_INTERVAL = config.captcha_adaptive_report_interval
CAPTCHA_PROBE_POOL_SIZE = config.captcha_probe_pool_size
CAPTCHA_PROBE_SHARE_POOL = config.captcha_probe_share_pool
CAPTCHA_SAMPLE_ENABLE = config.captcha_sample_enable
CAPTCHA_SAMPLE_RATE = config.captcha_sample_rate
CAPTCHA_SAMPLE_DIR = config.captcha_sample_dir
CAPTCHA_ADAPTIVE_UPDATE_INTERVAL = config.captcha_adaptive_update_interval
CAPTCHA_ADAPTIVE_FAIL_STREAK = config.captcha_adaptive_fail_streak_degrade
CAPTCHA_ADAPTIVE_SCORE_ALPHA = config.captcha_adaptive_score_alpha
CAPTCHA_ADAPTIVE_SCORE_BETA = config.captcha_adaptive_score_beta
RUNTIME_STAT_REPORT_INTERVAL = config.runtime_stat_report_interval
RUNTIME_RATE_WINDOW_SECONDS = config.runtime_rate_window_seconds
RUNTIME_ERROR_AGG_INTERVAL = config.runtime_error_aggregate_interval

adaptive = CaptchaAdaptiveManager(
    _recognizer_names,
    enabled=config.captcha_adaptive_enable,
    min_samples=config.captcha_adaptive_min_samples,
    epsilon=config.captcha_adaptive_epsilon,
    latency_alpha=config.captcha_adaptive_latency_alpha,
    h_alpha=config.captcha_adaptive_h_alpha,
    h_init=config.captcha_adaptive_h_init,
    update_interval=CAPTCHA_ADAPTIVE_UPDATE_INTERVAL,
    fail_streak_degrade=CAPTCHA_ADAPTIVE_FAIL_STREAK,
    score_alpha=CAPTCHA_ADAPTIVE_SCORE_ALPHA,
    score_beta=CAPTCHA_ADAPTIVE_SCORE_BETA,
)

OFFLINE_ENABLED = config.offline_enabled
OFFLINE_ERROR_THRESHOLD = config.offline_error_threshold
OFFLINE_COOLDOWN_SECONDS = config.offline_cooldown_seconds
OFFLINE_PROBE_INTERVAL = config.offline_probe_interval
OFFLINE_PROBE_TIMEOUT = config.offline_probe_timeout
OFFLINE_OBSERVE_SECONDS = config.offline_observe_seconds
OFFLINE_OBSERVE_MIN_REFRESH = config.offline_observe_min_refresh
NOT_IN_OPERATION_COOLDOWN_SECONDS = config.not_in_operation_cooldown_seconds
NOT_IN_OPERATION_MIN_REFRESH = config.not_in_operation_min_refresh
NOT_IN_OPERATION_SKIP_POOL_RESET = config.not_in_operation_skip_pool_reset
NOT_IN_OPERATION_DYNAMIC_ENABLE = getattr(config, "not_in_operation_dynamic_enable", True)
NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS = getattr(
    config, "not_in_operation_schedule_ttl_seconds", 6 * 3600.0
)
NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX = getattr(
    config, "not_in_operation_dynamic_long_sleep_max", 3600.0
)
HTML_PARSE_ERROR_THRESHOLD = config.html_parse_error_threshold
HTML_PARSE_COOLDOWN_SECONDS = config.html_parse_cooldown_seconds
HTML_PARSE_RESET_SESSIONS = config.html_parse_reset_sessions
AUTH_ERROR_THRESHOLD = config.auth_error_threshold
AUTH_COOLDOWN_SECONDS = config.auth_cooldown_seconds
AUTH_RESET_SESSIONS = config.auth_reset_sessions

CAPTCHA_ADAPTIVE_PERSIST_ENABLE = getattr(config, "captcha_adaptive_persist_enable", False)
CAPTCHA_ADAPTIVE_PERSIST_PATH = getattr(
    config, "captcha_adaptive_persist_path", "cache/captcha_adaptive_snapshot.json"
)
CAPTCHA_ADAPTIVE_PERSIST_INTERVAL_SECONDS = getattr(
    config, "captcha_adaptive_persist_interval_seconds", 60.0
)

WARMUP_AFTER_LOGIN_ENABLE = getattr(config, "warmup_after_login_enable", False)

RUNTIME_STAT_REPORT_INTERVAL = getattr(config, "runtime_stat_report_interval", 0)
electivePool = Queue(maxsize=elective_client_pool_size)
probePool = None
_probe_pool_shared = False
if CAPTCHA_PROBE_ENABLED:
    if CAPTCHA_PROBE_SHARE_POOL:
        probePool = electivePool
        _probe_pool_shared = True
    elif CAPTCHA_PROBE_POOL_SIZE > 0:
        probePool = Queue(maxsize=CAPTCHA_PROBE_POOL_SIZE)
probe_pool_extra = 0 if _probe_pool_shared else (CAPTCHA_PROBE_POOL_SIZE or 0)
reloginPool = Queue(maxsize=elective_client_pool_size + probe_pool_extra)

goals = environ.goals  # let N = len(goals);
ignored = environ.ignored
mutexes = np.zeros(0, dtype=np.uint8)  # uint8 [N][N];
delays = np.zeros(0, dtype=np.int32)  # int [N];

killedElective = ElectiveClient(-1)
NO_DELAY = -1
_captcha_failure_count = 0
_captcha_degrade_until = 0.0
_last_degrade_notify_at = 0.0
_iaaa_consecutive_errors = 0
_elective_consecutive_errors = 0
_last_pool_reset_at = 0.0
_client_generation = 0
_critical_cooldown_until = 0.0
_last_critical_notify_at = 0.0
_offline_active = False
_offline_next_probe_at = 0.0
_offline_error_streak = 0
_offline_observe_until = 0.0
_not_in_operation_streak = 0
_last_not_in_operation_at = 0.0
_html_parse_streak = 0
_auth_error_streak = 0
_sample_seq = 0
_sample_dir_ready = False
_pool_reset_lock = threading.Lock()
_stats_lock = threading.Lock()
_rate_lock = threading.Lock()
_error_agg_lock = threading.Lock()
_offline_lock = threading.Lock()
_offline_probe_lock = threading.Lock()
_sample_lock = threading.Lock()
_adaptive_persist_lock = threading.Lock()
_adaptive_persist_last_at = 0.0
_adaptive_snapshot_loaded = False
_help_schedule_lock = threading.Lock()
_help_schedule_fetched_at = 0.0
_help_schedule_items = None
_not_in_operation_min_refresh_dynamic = NOT_IN_OPERATION_MIN_REFRESH
_not_in_operation_backoff_reason = ""
_error_agg_last = 0.0
_error_agg_counts = defaultdict(int)
_RATE_KEYS = {
    "probe_attempt",
    "probe_success",
    "probe_fail",
    "captcha_attempt",
    "captcha_validate_pass",
    "captcha_validate_fail",
}
_rate_events = {k: deque() for k in _RATE_KEYS}

notify.send_bark_push(msg=WECHAT_MSG["s"], prefix=WECHAT_PREFIX[3])

# resilience config
CRITICAL_COOLDOWN_SECONDS = config.critical_cooldown_seconds
CRITICAL_NOTIFY_INTERVAL = config.critical_notify_interval
CRITICAL_RESET_CACHE = config.critical_reset_cache
CRITICAL_RESET_SESSIONS = config.critical_reset_sessions
FAILURE_NOTIFY_THRESHOLD = config.failure_notify_threshold
FAILURE_NOTIFY_INTERVAL = config.failure_notify_interval
FAILURE_COOLDOWN_SECONDS = config.failure_cooldown_seconds


class _ElectiveNeedsLogin(Exception):
    pass


class _ElectiveExpired(Exception):
    pass


def _get_refresh_interval():
    if refresh_random_deviation <= 0:
        return max(MIN_REFRESH_INTERVAL, refresh_interval)
    delta = (random.random() * 2 - 1) * refresh_random_deviation * refresh_interval
    return max(MIN_REFRESH_INTERVAL, refresh_interval + delta)


def _get_probe_interval():
    if CAPTCHA_PROBE_INTERVAL <= 0:
        return None
    if CAPTCHA_PROBE_RANDOM_DEV <= 0:
        return max(1.0, CAPTCHA_PROBE_INTERVAL)
    delta = (random.random() * 2 - 1) * CAPTCHA_PROBE_RANDOM_DEV * CAPTCHA_PROBE_INTERVAL
    return max(1.0, CAPTCHA_PROBE_INTERVAL + delta)


def _compute_backoff(base, errors, threshold, factor, max_extra):
    if errors <= 0:
        return base
    if errors < threshold:
        return base
    exp = errors - threshold + 1
    extra = base * (factor ** exp - 1.0)
    extra = min(max_extra, max(0.0, extra))
    return base + extra


def _apply_not_in_operation_backoff(base_sleep, had_not_in_operation):
    if not had_not_in_operation:
        return base_sleep
    mr = _not_in_operation_min_refresh_dynamic
    if mr is None:
        mr = NOT_IN_OPERATION_MIN_REFRESH
    if mr <= 0:
        return base_sleep
    return max(base_sleep, mr)


_re_cn_datetime = re.compile(
    r"(?:(?P<y>\\d{4})年)?(?P<m>\\d{1,2})月(?P<d>\\d{1,2})日"
    r"(?:(?P<ap>上午|下午|晚上|中午))?(?P<h>\\d{1,2}):(?P<min>\\d{2})"
)
_re_iso_datetime = re.compile(
    r"(?P<y>\\d{4})[-/](?P<m>\\d{1,2})[-/](?P<d>\\d{1,2})\\s+(?P<h>\\d{1,2}):(?P<min>\\d{2})"
)


def _parse_cn_dt(text, now_ts=None):
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    mat = _re_iso_datetime.search(s)
    if mat:
        try:
            y = int(mat.group("y"))
            m = int(mat.group("m"))
            d = int(mat.group("d"))
            hh = int(mat.group("h"))
            mm = int(mat.group("min"))
            return datetime(y, m, d, hh, mm, 0).timestamp()
        except Exception:
            return None
    mat = _re_cn_datetime.search(s)
    if not mat:
        return None
    try:
        now = time.localtime(now_ts or time.time())
        y = mat.group("y")
        y = int(y) if y else int(now.tm_year)
        m = int(mat.group("m"))
        d = int(mat.group("d"))
        ap = mat.group("ap") or ""
        hh = int(mat.group("h"))
        mm = int(mat.group("min"))
        if ap in ("下午", "晚上", "中午") and hh < 12:
            hh += 12
        ts = datetime(y, m, d, hh, mm, 0).timestamp()
        # Heuristic for year rollover (e.g., Dec -> next year's Jan)
        if now_ts is not None and ts < now_ts - 7 * 86400 and m < now.tm_mon:
            ts = datetime(y + 1, m, d, hh, mm, 0).timestamp()
        return ts
    except Exception:
        return None


def _parse_help_schedule(tree, now_ts=None):
    """
    Parse operation schedule from HelpController.jpf.
    Returns list of dicts: {name, start_ts, end_ts}.
    """
    try:
        tables = get_tables(tree)
    except Exception:
        tables = []

    def _find_col(header, keywords):
        for kw in keywords:
            for i, h in enumerate(header):
                try:
                    if kw in h:
                        return i
                except Exception:
                    continue
        return None

    items = []
    for tbl in tables:
        header = tbl.xpath('.//tr[@class="datagrid-header"]/th/text()')
        if not header:
            continue
        start_ix = _find_col(header, ["开始时间", "开始"])
        end_ix = _find_col(header, ["结束时间", "结束"])
        if start_ix is None or end_ix is None:
            continue
        name_ix = _find_col(header, ["项目", "阶段", "选课阶段", "内容"])
        if name_ix is None:
            name_ix = 0
        trs = tbl.xpath('.//tr[@class="datagrid-odd" or @class="datagrid-even"]')
        for tr in trs:
            tds = tr.xpath("./th | ./td")
            if not tds:
                continue
            try:
                name = "".join(tds[name_ix].xpath(".//text()")).strip()
                start_s = "".join(tds[start_ix].xpath(".//text()")).strip()
                end_s = "".join(tds[end_ix].xpath(".//text()")).strip()
            except Exception:
                continue
            start_ts = _parse_cn_dt(start_s, now_ts=now_ts)
            end_ts = _parse_cn_dt(end_s, now_ts=now_ts)
            if not name or start_ts is None or end_ts is None:
                continue
            items.append({"name": name, "start_ts": start_ts, "end_ts": end_ts})
    return items


def _get_help_schedule(elective=None, force_refresh=False):
    global _help_schedule_fetched_at, _help_schedule_items
    if not NOT_IN_OPERATION_DYNAMIC_ENABLE:
        return None
    now = time.time()
    try:
        with _help_schedule_lock:
            if (
                not force_refresh
                and _help_schedule_items is not None
                and NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS > 0
                and now - _help_schedule_fetched_at < NOT_IN_OPERATION_SCHEDULE_TTL_SECONDS
            ):
                return list(_help_schedule_items)
    except Exception:
        pass
    if elective is None:
        return _help_schedule_items
    try:
        r = elective.get_HelpController()
        items = _parse_help_schedule(getattr(r, "_tree", None), now_ts=now)
        if items:
            with _help_schedule_lock:
                _help_schedule_items = list(items)
                _help_schedule_fetched_at = now
        return items or _help_schedule_items
    except Exception as e:
        ferr.error(e)
        return _help_schedule_items


def _find_next_operation_start(now_ts, schedule_items):
    if not schedule_items:
        return None
    candidates = []
    for it in schedule_items:
        try:
            name = it.get("name") or ""
            start_ts = float(it.get("start_ts"))
        except Exception:
            continue
        if start_ts <= now_ts:
            continue
        if "补退选" in name or "候补" in name or "补选" in name:
            candidates.append(it)
    if not candidates:
        return None
    return min(candidates, key=lambda x: x.get("start_ts", float("inf")))


def _update_not_in_operation_backoff(elective=None):
    """
    Update dynamic backoff when we hit NotInOperationTimeError.
    Only increases sleep to reduce useless traffic before operation begins.
    """
    global _not_in_operation_min_refresh_dynamic, _not_in_operation_backoff_reason
    now = time.time()
    mr = NOT_IN_OPERATION_MIN_REFRESH
    cooldown = NOT_IN_OPERATION_COOLDOWN_SECONDS
    reason = "static"

    if NOT_IN_OPERATION_DYNAMIC_ENABLE:
        sched = _get_help_schedule(elective=elective)
        nxt = _find_next_operation_start(now, sched)
        if nxt is not None:
            start_ts = float(nxt["start_ts"])
            delta = max(0.0, start_ts - now)
            # Piecewise policy: far away -> long sleep; near -> keep base config.
            if delta >= 24 * 3600:
                computed = min(NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX, 1800.0)
            elif delta >= 6 * 3600:
                computed = min(NOT_IN_OPERATION_DYNAMIC_LONG_SLEEP_MAX, 600.0)
            elif delta >= 2 * 3600:
                computed = 120.0
            elif delta >= 30 * 60:
                computed = 30.0
            elif delta >= 5 * 60:
                computed = 10.0
            else:
                computed = mr
            mr = max(mr, computed)
            cooldown = min(max(0.0, cooldown), mr)
            try:
                start_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                start_str = str(start_ts)
            reason = "next=%s@%s, delta=%ss" % (nxt.get("name"), start_str, int(delta))

    _not_in_operation_min_refresh_dynamic = mr
    _not_in_operation_backoff_reason = reason
    _stat_set_gauge("not_in_operation_min_refresh", mr)
    if cooldown and cooldown > 0:
        _enter_cooldown("not_in_operation", cooldown)
    return mr, reason


def _adaptive_persist_path_abs():
    path = (CAPTCHA_ADAPTIVE_PERSIST_PATH or "").strip()
    if not path:
        return None
    # Use cwd-relative path by default (repo root).
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.abspath(path))


def _load_adaptive_snapshot_once():
    global _adaptive_snapshot_loaded
    if _adaptive_snapshot_loaded:
        return False
    _adaptive_snapshot_loaded = True
    if not CAPTCHA_ADAPTIVE_PERSIST_ENABLE:
        return False
    path = _adaptive_persist_path_abs()
    if not path:
        return False
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = stdjson.load(fp)
        snap = data.get("snapshot") if isinstance(data, dict) else None
        if snap is None and isinstance(data, dict):
            snap = data
        ok = adaptive.load_snapshot(snap)
        if ok:
            _stat_inc("adaptive_persist_load")
            cout.info("Adaptive snapshot loaded: %s" % path)
        return ok
    except FileNotFoundError:
        return False
    except Exception as e:
        ferr.error(e)
        return False


def _maybe_persist_adaptive(force=False):
    global _adaptive_persist_last_at
    if not CAPTCHA_ADAPTIVE_PERSIST_ENABLE:
        return False
    interval = float(CAPTCHA_ADAPTIVE_PERSIST_INTERVAL_SECONDS or 0.0)
    now = time.time()
    if not force and interval > 0 and (now - _adaptive_persist_last_at) < interval:
        return False
    if not _adaptive_persist_lock.acquire(blocking=False):
        return False
    try:
        if not force and interval > 0 and (now - _adaptive_persist_last_at) < interval:
            return False
        _adaptive_persist_last_at = now
        snap = adaptive.snapshot()
        payload = {"saved_at": now, "snapshot": snap}
        path = _adaptive_persist_path_abs()
        if not path:
            return False
        d = os.path.dirname(path)
        if d:
            mkdir(d)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            stdjson.dump(payload, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        _stat_inc("adaptive_persist_write")
        _stat_set_gauge("adaptive_persist_last_at", int(now))
        return True
    except Exception as e:
        ferr.error(e)
        return False
    finally:
        _adaptive_persist_lock.release()


def _is_stale_client(client):
    gen = getattr(client, "_gen", None)
    if gen is None:
        return False
    return gen != _client_generation


def _make_client(id, pool_kind="elective"):
    c = ElectiveClient(id=id, timeout=elective_client_timeout)
    c.set_user_agent(random.choice(USER_AGENT_LIST))
    c._gen = _client_generation
    c._pool_kind = pool_kind
    return c


def _make_probe_client(id):
    return _make_client(id, pool_kind="probe")


def _client_pool_kind(client):
    return getattr(client, "_pool_kind", "elective")


def _return_client_home(client):
    kind = _client_pool_kind(client)
    if kind == "probe" and probePool is not None and not _probe_pool_shared:
        _return_client(probePool, client, "probePool")
    else:
        _return_client(electivePool, client, "electivePool")


def _return_client(queue, client, name):
    if client is None:
        return
    if client is killedElective:
        _safe_put(queue, client, name)
        return
    if _is_stale_client(client):
        _stat_inc("client_stale_drop")
        return
    _safe_put(queue, client, name)


def _reset_client_pool(reason, force=False):
    global _client_generation, _last_pool_reset_at
    if not _pool_reset_lock.acquire(blocking=False):
        _stat_inc("pool_reset_skipped_lock")
        return False
    try:
        now = time.time()
        if not force and CLIENT_POOL_RESET_COOLDOWN > 0 and (now - _last_pool_reset_at) < CLIENT_POOL_RESET_COOLDOWN:
            _stat_inc("pool_reset_skipped_cooldown")
            return False
        _client_generation += 1
        _last_pool_reset_at = now
        _stat_inc("pool_reset_count")
        _stat_set_gauge("pool_reset_generation", _client_generation)
        cout.warning("Reset elective client pool (%s)" % reason)

        # Drain pools
        while True:
            try:
                electivePool.get_nowait()
            except Empty:
                break
        if probePool is not None and not _probe_pool_shared:
            while True:
                try:
                    probePool.get_nowait()
                except Empty:
                    break
        while True:
            try:
                reloginPool.get_nowait()
            except Empty:
                break

        for ix in range(1, elective_client_pool_size + 1):
            _safe_put(electivePool, _make_client(ix), "electivePool")
        if probePool is not None and not _probe_pool_shared:
            for ix in range(1, CAPTCHA_PROBE_POOL_SIZE + 1):
                _safe_put(probePool, _make_probe_client(ix), "probePool")
        _stat_set_gauge("elective_pool_qsize", electivePool.qsize())
        if probePool is not None:
            _stat_set_gauge("probe_pool_qsize", probePool.qsize())
        _stat_set_gauge("relogin_pool_qsize", reloginPool.qsize())
        return True
    finally:
        _pool_reset_lock.release()


def _ignore_course(course, reason):
    ignored[course.to_simplified()] = reason


def _add_error(e):
    clz = e.__class__
    name = clz.__name__
    key = "[%s] %s" % (e.code, name) if hasattr(clz, "code") else name
    environ.errors[key] += 1
    _error_agg_record(key)


def _format_timestamp(timestamp):
    if timestamp == -1:
        return str(timestamp)
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

def _snapshot_runtime_stats():
    try:
        with _stats_lock:
            stats = dict(environ.runtime_stats)
            gauges = dict(environ.runtime_gauges)
        return stats, gauges
    except Exception:
        return {}, {}

def _rate_record(key):
    if RUNTIME_RATE_WINDOW_SECONDS <= 0:
        return
    if key not in _RATE_KEYS:
        return
    now = time.time()
    try:
        with _rate_lock:
            dq = _rate_events.get(key)
            if dq is None:
                dq = deque()
                _rate_events[key] = dq
            dq.append(now)
            cutoff = now - RUNTIME_RATE_WINDOW_SECONDS
            while dq and dq[0] < cutoff:
                dq.popleft()
    except Exception:
        pass


def _rate_snapshot():
    if RUNTIME_RATE_WINDOW_SECONDS <= 0:
        return {}
    now = time.time()
    rates = {}
    try:
        with _rate_lock:
            cutoff = now - RUNTIME_RATE_WINDOW_SECONDS
            for k, dq in _rate_events.items():
                while dq and dq[0] < cutoff:
                    dq.popleft()
                rates[k] = len(dq) / float(RUNTIME_RATE_WINDOW_SECONDS)
    except Exception:
        return {}
    return rates


def _error_agg_record(key):
    if RUNTIME_ERROR_AGG_INTERVAL <= 0:
        return
    try:
        with _error_agg_lock:
            _error_agg_counts[key] += 1
    except Exception:
        pass


def _maybe_report_error_agg():
    global _error_agg_last
    if RUNTIME_ERROR_AGG_INTERVAL <= 0:
        return
    now = time.time()
    if now - _error_agg_last < RUNTIME_ERROR_AGG_INTERVAL:
        return
    try:
        with _error_agg_lock:
            if not _error_agg_counts:
                _error_agg_last = now
                return
            snapshot = dict(_error_agg_counts)
            _error_agg_counts.clear()
            _error_agg_last = now
    except Exception:
        return
    items = sorted(snapshot.items(), key=lambda kv: kv[1], reverse=True)
    top = items[:10]
    summary = ", ".join("%s x%d" % (k, v) for k, v in top)
    cout.warning("error_agg(%.0fs): %s" % (RUNTIME_ERROR_AGG_INTERVAL, summary))
    if len(items) > 10:
        cout.warning("error_agg: ... total=%d" % len(items))


def _report_runtime_stats():
    stats, gauges = _snapshot_runtime_stats()
    rates = _rate_snapshot()
    for k, v in rates.items():
        _stat_set_gauge("rate_" + k, round(v, 4))
    if rates:
        # refresh gauges snapshot after rate update
        stats, gauges = _snapshot_runtime_stats()
    if not stats and not gauges:
        return
    def _format_items(items):
        return ", ".join("%s=%s" % (k, items[k]) for k in sorted(items.keys()))

    def _group_by_prefix(data, groups):
        remaining = dict(data)
        result = []
        for label, prefixes in groups:
            picked = {}
            for k in list(remaining.keys()):
                if any(k.startswith(p) for p in prefixes):
                    picked[k] = remaining.pop(k)
            if picked:
                result.append((label, picked))
        if remaining:
            result.append(("other", remaining))
        return result

    stat_groups = _group_by_prefix(
        stats,
        [
            ("pool", ("pool_", "queue_", "client_")),
            ("probe", ("probe_",)),
            ("captcha", ("captcha_",)),
            ("offline", ("offline_",)),
            ("net", ("net_error_",)),
            ("html", ("html_",)),
            ("auth", ("auth_",)),
        ],
    )
    gauge_groups = _group_by_prefix(
        gauges,
        [
            ("pool", ("elective_pool_", "relogin_pool_", "probe_pool_", "pool_reset_")),
            ("errors", ("elective_consecutive_", "iaaa_consecutive_")),
            ("rate", ("rate_",)),
            ("offline", ("offline_",)),
            ("not_in_operation", ("not_in_operation_",)),
            ("auth", ("auth_",)),
            ("html", ("html_",)),
        ],
    )

    for label, items in stat_groups:
        cout.info("runtime_stats.%s: %s" % (label, _format_items(items)))
    for label, items in gauge_groups:
        cout.info("runtime_gauges.%s: %s" % (label, _format_items(items)))

def _stat_inc(key, delta=1):
    if delta == 0:
        return
    try:
        with _stats_lock:
            environ.runtime_stats[key] += delta
    except Exception:
        pass
    _rate_record(key)


def _stat_set_gauge(key, value):
    try:
        with _stats_lock:
            environ.runtime_gauges[key] = value
    except Exception:
        pass

rate_limit.configure(config)
rate_limit.set_stat_hooks(_stat_inc, _stat_set_gauge)

def _captcha_is_degraded():
    return time.time() < _captcha_degrade_until

def _record_captcha_success():
    global _captcha_failure_count
    _captcha_failure_count = 0

def _record_captcha_failure():
    global _captcha_failure_count, _captcha_degrade_until
    _captcha_failure_count += 1
    if CAPTCHA_DEGRADE_FAILURES > 0 and _captcha_failure_count >= CAPTCHA_DEGRADE_FAILURES:
        _captcha_degrade_until = time.time() + CAPTCHA_DEGRADE_COOLDOWN
        _captcha_failure_count = 0
        cout.warning(
            "Captcha recognition degraded for %s s" % int(CAPTCHA_DEGRADE_COOLDOWN)
        )
        if CAPTCHA_SWITCH_ON_DEGRADE:
            _rotate_recognizer("degraded")
        if CAPTCHA_DEGRADE_NOTIFY:
            _notify_degraded("Captcha degraded")


def _ensure_sample_dir():
    global _sample_dir_ready
    if _sample_dir_ready:
        return True
    try:
        mkdir(CAPTCHA_SAMPLE_DIR)
        _sample_dir_ready = True
    except Exception:
        _sample_dir_ready = False
    return _sample_dir_ready


def _guess_image_ext(raw):
    if not raw:
        return "bin"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8"):
        return "jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if raw.startswith(b"BM"):
        return "bmp"
    return "bin"


def _maybe_sample_captcha(raw, provider=None, context=None, draw_dt=None):
    if not CAPTCHA_SAMPLE_ENABLE:
        return
    if raw is None:
        return
    if CAPTCHA_SAMPLE_RATE < 1.0 and random.random() > CAPTCHA_SAMPLE_RATE:
        return
    if not _ensure_sample_dir():
        return
    try:
        ext = _guess_image_ext(raw)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        h = hashlib.sha1(raw).hexdigest()[:12]
        with _sample_lock:
            global _sample_seq
            _sample_seq += 1
            seq = _sample_seq
        base = "%s_%s_%d" % (ts, h, seq)
        img_path = os.path.join(CAPTCHA_SAMPLE_DIR, base + "." + ext)
        meta_path = os.path.join(CAPTCHA_SAMPLE_DIR, base + ".json")
        with open(img_path, "wb") as fp:
            fp.write(raw)
        meta = {
            "ts": ts,
            "provider": provider,
            "context": context,
            "loop": environ.elective_loop,
            "draw_dt": draw_dt,
            "size": len(raw),
        }
        with open(meta_path, "w", encoding="utf-8") as fp:
            fp.write(stdjson.dumps(meta, ensure_ascii=False))
        _stat_inc("captcha_sample_saved")
    except Exception:
        _stat_inc("captcha_sample_error")


def _apply_recognizer_order(new_order, reason=None, switch_primary=False):
    global _recognizer_names, recognizers, recognizer_index, recognizer
    if not new_order:
        return False
    order = []
    seen = set()
    for name in new_order:
        if name in _recognizer_map and name not in seen:
            seen.add(name)
            order.append(name)
    if not order:
        return False
    if order == _recognizer_names:
        return False
    old_names = list(_recognizer_names)
    old_current = _recognizer_names[recognizer_index]
    _recognizer_names = order
    recognizers = [_recognizer_map[n] for n in _recognizer_names]

    if switch_primary:
        recognizer_index = 0
    else:
        if old_current in _recognizer_names:
            recognizer_index = _recognizer_names.index(old_current)
        else:
            recognizer_index = 0

    recognizer = recognizers[recognizer_index]
    adaptive.update_order(_recognizer_names)

    if reason:
        cout.warning(
            "Adaptive reorder (%s): %s -> %s"
            % (reason, ",".join(old_names), ",".join(_recognizer_names))
        )
    return True


def _maybe_adaptive_reorder(reason):
    try:
        new_order, switch_primary, changed = adaptive.maybe_reorder(
            _recognizer_names, loop_count=environ.elective_loop
        )
        if changed:
            _apply_recognizer_order(new_order, reason=reason, switch_primary=switch_primary)
        return changed
    except Exception as e:
        ferr.error(e)
        return False


def _report_adaptive_state():
    if not adaptive.enabled:
        return
    try:
        snap = adaptive.snapshot()
        order = snap.get("providers") or []
        h_val = snap.get("h")
        cout.info("Adaptive order: %s" % ",".join(order))
        if h_val is not None:
            cout.info("Adaptive H: %.3f" % h_val)
        stats = snap.get("stats") or {}
        cout.info("Adaptive stats:")
        cout.info("  provider | count | succ | fail | streak | p_hat | t_hat | h_hat | score")
        for name in order:
            st = stats.get(name) or {}
            count = st.get("count", 0)
            succ = st.get("success", 0)
            fail = st.get("failure", 0)
            streak = st.get("fail_streak", 0)
            p_hat = st.get("p_hat")
            lat = st.get("latency")
            h_hat = st.get("h_latency")
            score = st.get("score")
            cout.info(
                "  %-8s | %5d | %4d | %4d | %6d | %5s | %5s | %5s | %5s"
                % (
                    name,
                    count,
                    succ,
                    fail,
                    streak,
                    "%.3f" % p_hat if p_hat is not None else "--",
                    "%.3f" % lat if lat is not None else "--",
                    "%.3f" % h_hat if h_hat is not None else "--",
                    "%.3f" % score if score is not None else "--",
                )
            )

        eligible = [(name, (stats.get(name) or {}).get("score")) for name in order]
        eligible = [(n, s) for n, s in eligible if s is not None]
        if not eligible:
            cout.info(
                "Adaptive reason: cold-start (min_samples=%d); apply fail-streak degrade=%d"
                % (config.captcha_adaptive_min_samples, CAPTCHA_ADAPTIVE_FAIL_STREAK)
            )
        else:
            ranked = sorted(eligible, key=lambda x: x[1], reverse=True)
            recommend = [n for n, _ in ranked]
            cur = order[0] if order else None
            best = ranked[0][0] if ranked else None
            cur_score = dict(ranked).get(cur)
            best_score = dict(ranked).get(best)
            reason = "score desc (score=p_hat-%.2f*t-%.2f*h)" % (
                CAPTCHA_ADAPTIVE_SCORE_ALPHA,
                CAPTCHA_ADAPTIVE_SCORE_BETA,
            )
            if cur and best and cur_score is not None and best_score is not None:
                if best != cur and best_score >= cur_score * (1.0 + config.captcha_adaptive_epsilon):
                    reason += "; recommend switch %s->%s (%.3f -> %.3f, eps=%.2f)" % (
                        cur,
                        best,
                        cur_score,
                        best_score,
                        config.captcha_adaptive_epsilon,
                    )
                else:
                    reason += "; keep %s (eps=%.2f)" % (cur, config.captcha_adaptive_epsilon)
            cout.info("Adaptive recommend: %s" % " > ".join(recommend))
            cout.info("Adaptive reason: %s" % reason)
    except Exception as e:
        ferr.error(e)

def _rotate_recognizer(reason):
    global recognizer_index, recognizer
    if len(recognizers) <= 1:
        return False
    old = _recognizer_names[recognizer_index]
    recognizer_index = (recognizer_index + 1) % len(recognizers)
    recognizer = recognizers[recognizer_index]
    new = _recognizer_names[recognizer_index]
    if old == new:
        return False
    cout.warning("Rotate recognizer %s -> %s (%s)" % (old, new, reason))
    return True

def _notify_degraded(title):
    global _last_degrade_notify_at
    now = time.time()
    if now - _last_degrade_notify_at < CAPTCHA_DEGRADE_NOTIFY_INTERVAL:
        return
    _last_degrade_notify_at = now
    try:
        notify.send_bark_push(msg=title, prefix=WECHAT_PREFIX[3])
    except Exception:
        pass


def _notify_resilience(title):
    if not FAILURE_NOTIFY_INTERVAL and not CRITICAL_NOTIFY_INTERVAL:
        return
    try:
        notify.send_bark_push(msg=title, prefix=WECHAT_PREFIX[3])
    except Exception:
        pass


def _maybe_failure_notify(count, title):
    global _last_critical_notify_at
    if FAILURE_NOTIFY_THRESHOLD <= 0:
        return
    if count < FAILURE_NOTIFY_THRESHOLD:
        return
    now = time.time()
    interval = FAILURE_NOTIFY_INTERVAL
    if interval <= 0:
        return
    if now - _last_critical_notify_at < interval:
        return
    _last_critical_notify_at = now
    _notify_resilience(title)


def _enter_cooldown(reason, seconds):
    global _critical_cooldown_until
    if seconds <= 0:
        return
    _critical_cooldown_until = time.time() + seconds
    cout.warning("Enter cooldown for %s s (%s)" % (int(seconds), reason))


def _maybe_cooldown_sleep():
    if _critical_cooldown_until <= 0:
        return
    now = time.time()
    if now >= _critical_cooldown_until:
        return
    sleep_s = min(5.0, _critical_cooldown_until - now)
    time.sleep(max(0.0, sleep_s))


def _is_network_error(e):
    return isinstance(e, (RequestException, OperationTimeoutError))


def _enter_offline(reason):
    global _offline_active, _offline_next_probe_at, _offline_error_streak, _offline_observe_until
    if not OFFLINE_ENABLED:
        return
    now = time.time()
    with _offline_lock:
        if _offline_active:
            return
        _offline_active = True
        _offline_error_streak = 0
        _offline_next_probe_at = now + max(0.0, OFFLINE_COOLDOWN_SECONDS)
        _offline_observe_until = 0.0
    _stat_inc("offline_enter")
    _stat_set_gauge("offline_active", 1)
    _stat_set_gauge("offline_observe_active", 0)
    cout.warning(
        "Enter OFFLINE (reason=%s, next_probe_in=%ss)"
        % (reason, int(max(0.0, OFFLINE_COOLDOWN_SECONDS)))
    )


def _exit_offline(reason):
    global _offline_active, _offline_next_probe_at, _offline_error_streak, _offline_observe_until
    with _offline_lock:
        _offline_active = False
        _offline_next_probe_at = 0.0
        _offline_error_streak = 0
        if OFFLINE_OBSERVE_SECONDS > 0:
            _offline_observe_until = time.time() + OFFLINE_OBSERVE_SECONDS
        else:
            _offline_observe_until = 0.0
    _stat_inc("offline_recover")
    _stat_set_gauge("offline_active", 0)
    _stat_set_gauge("offline_observe_active", 1 if OFFLINE_OBSERVE_SECONDS > 0 else 0)
    cout.warning("Exit OFFLINE (%s)" % reason)


def _record_network_error(reason):
    global _offline_error_streak
    if not OFFLINE_ENABLED:
        return
    with _offline_lock:
        if _offline_active:
            return
        _offline_error_streak += 1
        if _offline_error_streak < OFFLINE_ERROR_THRESHOLD:
            return
    _enter_offline(reason)


def _record_network_success():
    global _offline_error_streak
    if not OFFLINE_ENABLED:
        return
    with _offline_lock:
        if _offline_active:
            return
        _offline_error_streak = 0


def _offline_health_probe():
    try:
        iaaa = IAAAClient(timeout=OFFLINE_PROBE_TIMEOUT)
        iaaa.set_user_agent(random.choice(USER_AGENT_LIST))
        iaaa.oauth_home()
        return True
    except Exception:
        return False


def _offline_is_active():
    with _offline_lock:
        return _offline_active


def _offline_in_observe():
    global _offline_observe_until
    if OFFLINE_OBSERVE_SECONDS <= 0:
        return False
    with _offline_lock:
        if _offline_observe_until <= 0:
            return False
        if _offline_observe_until <= time.time():
            _offline_observe_until = 0.0
            _stat_set_gauge("offline_observe_active", 0)
            return False
        return True


def _apply_offline_observe_delay(base_sleep):
    if not _offline_in_observe():
        return base_sleep
    if OFFLINE_OBSERVE_MIN_REFRESH <= 0:
        return base_sleep
    return max(base_sleep, OFFLINE_OBSERVE_MIN_REFRESH)


def _iter_exc_chain(exc):
    seen = set()
    e = exc
    while e is not None and id(e) not in seen:
        yield e
        seen.add(id(e))
        e = getattr(e, "__cause__", None) or getattr(e, "__context__", None)


def _classify_network_error(exc):
    if isinstance(exc, OperationTimeoutError):
        return "timeout"
    chain = list(_iter_exc_chain(exc))
    if any(isinstance(e, Timeout) for e in chain):
        return "timeout"
    if any(isinstance(e, SSLError) for e in chain):
        return "tls"
    if any(isinstance(e, socket.gaierror) for e in chain):
        return "dns"
    msg = str(exc).lower()
    dns_hints = (
        "name or service not known",
        "temporary failure in name resolution",
        "nodename nor servname provided",
        "no address associated with hostname",
        "unknown host",
    )
    if any(hint in msg for hint in dns_hints):
        return "dns"
    if "ssl" in msg or "tls" in msg:
        return "tls"
    if any(isinstance(e, ConnectionError) for e in chain):
        return "conn"
    return "other"


def _record_network_error_detail(reason, exc=None):
    category = None
    if exc is not None:
        try:
            category = _classify_network_error(exc)
        except Exception:
            category = None
    if category:
        _stat_inc("net_error_%s" % category)
    _stat_inc("net_error_total")
    _record_network_error(reason)


def _record_html_parse_error(reason=None, count_stat=True):
    global _html_parse_streak
    if count_stat:
        _stat_inc("html_parse_error")
    _html_parse_streak += 1
    _stat_set_gauge("html_parse_streak", _html_parse_streak)
    if HTML_PARSE_ERROR_THRESHOLD > 0 and _html_parse_streak >= HTML_PARSE_ERROR_THRESHOLD:
        _stat_inc("html_parse_trigger")
        _html_parse_streak = 0
        _stat_set_gauge("html_parse_streak", 0)
        if HTML_PARSE_RESET_SESSIONS:
            _reset_client_pool("html_parse")
        if HTML_PARSE_COOLDOWN_SECONDS > 0:
            _enter_cooldown("html_parse", HTML_PARSE_COOLDOWN_SECONDS)


def _record_html_parse_success():
    global _html_parse_streak
    if _html_parse_streak != 0:
        _html_parse_streak = 0
        _stat_set_gauge("html_parse_streak", 0)


def _record_auth_error(reason=None):
    global _auth_error_streak
    _stat_inc("auth_error")
    _auth_error_streak += 1
    _stat_set_gauge("auth_error_streak", _auth_error_streak)
    if AUTH_ERROR_THRESHOLD > 0 and _auth_error_streak >= AUTH_ERROR_THRESHOLD:
        _stat_inc("auth_trigger")
        _auth_error_streak = 0
        _stat_set_gauge("auth_error_streak", 0)
        if AUTH_RESET_SESSIONS:
            _reset_client_pool("auth_error")
        if AUTH_COOLDOWN_SECONDS > 0:
            _enter_cooldown("auth_error", AUTH_COOLDOWN_SECONDS)


def _record_auth_success():
    global _auth_error_streak
    if _auth_error_streak != 0:
        _auth_error_streak = 0
        _stat_set_gauge("auth_error_streak", 0)


def _offline_tick(pause_event=None):
    global _offline_next_probe_at
    if not OFFLINE_ENABLED:
        return False
    with _offline_lock:
        active = _offline_active
        next_probe_at = _offline_next_probe_at
    if not active:
        return False
    # allow exit if no tasks remain
    try:
        current = [c for c in goals if c not in ignored]
    except Exception:
        current = []
    if len(current) == 0:
        return False
    if pause_event is not None:
        pause_event.set()
    now = time.time()
    if now < next_probe_at:
        time.sleep(min(1.0, next_probe_at - now))
        return True
    if not _offline_probe_lock.acquire(blocking=False):
        time.sleep(0.2)
        return True
    try:
        with _offline_lock:
            if not _offline_active:
                return False
            _offline_next_probe_at = time.time() + max(1.0, OFFLINE_PROBE_INTERVAL)
        _stat_inc("offline_probe_attempt")
        if _offline_health_probe():
            _stat_inc("offline_probe_success")
            cout.warning(
                "OFFLINE probe OK, recover; observe=%ss"
                % int(max(0.0, OFFLINE_OBSERVE_SECONDS))
            )
            _exit_offline("probe_ok")
            if pause_event is not None:
                pause_event.clear()
            _reset_client_pool("offline_recover", force=True)
            return False
        _stat_inc("offline_probe_fail")
        cout.warning(
            "OFFLINE probe failed, next in %ss" % int(max(1.0, OFFLINE_PROBE_INTERVAL))
        )
        return True
    finally:
        _offline_probe_lock.release()


def _reset_runtime_state(reason):
    if CRITICAL_RESET_SESSIONS:
        _reset_client_pool(reason)
    if CRITICAL_RESET_CACHE:
        adaptive.set_frozen(False)

def _notify_degraded_available(tasks):
    if not CAPTCHA_DEGRADE_NOTIFY:
        return
    if not tasks:
        return
    items = []
    for _, c in list(tasks)[:5]:
        items.append("%s[%s]" % (c.name, c.class_no))
    courses = ", ".join(items)
    if len(tasks) > 5:
        courses = courses + " ..."
    _notify_degraded("Available (degraded): %s" % courses)


def _run_captcha_probe_loop(stop_event, pause_event):
    if not CAPTCHA_PROBE_ENABLED:
        return
    if probePool is None:
        cout.warning("CaptchaProbe disabled: probe pool not configured")
        return
    probe_recognizers = {}
    next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)

    while not stop_event.is_set():
        if pause_event.is_set() or _captcha_is_degraded():
            time.sleep(0.5)
            continue

        now = time.time()
        if now < next_probe_at:
            time.sleep(min(0.5, next_probe_at - now))
            continue

        provider_order = adaptive.get_order()
        provider = adaptive.select_probe_provider(provider_order)
        if not provider:
            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
            continue

        try:
            client = probePool.get_nowait()
        except Empty:
            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
            continue
        if _is_stale_client(client):
            _stat_inc("client_stale_drop")
            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
            continue
        if not client.has_logined or client.is_expired:
            _return_client(reloginPool, client, "reloginPool")
            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
            continue

        try:
            if not client.has_logined or client.is_expired:
                _return_client(reloginPool, client, "reloginPool")
                client = None
                next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
                continue

            recognizer = probe_recognizers.get(provider)
            if recognizer is None:
                recognizer = get_recognizer(provider)
                probe_recognizers[provider] = recognizer

            t0 = time.time()
            try:
                r = client.get_DrawServlet()
            except (
                SessionExpiredError,
                InvalidTokenError,
                NoAuthInfoError,
                SharedSessionError,
                OperationTimeoutError,
            ) as e:
                ferr.error(e)
                _add_error(e)
                _record_auth_error("probe_auth")
                _stat_inc("probe_auth_error")
                _return_client(reloginPool, client, "reloginPool")
                client = None
                next_probe_at = time.time() + CAPTCHA_PROBE_BACKOFF
                continue
            except NotInOperationTimeError:
                _stat_inc("probe_not_in_operation")
                old_mr = _not_in_operation_min_refresh_dynamic
                old_reason = _not_in_operation_backoff_reason
                mr, reason = _update_not_in_operation_backoff(elective=client)
                if reason != old_reason or mr != old_mr:
                    cout.warning(
                        "Not in operation time (probe): min_refresh=%ss (%s)"
                        % (int(mr), reason)
                    )
                next_probe_at = time.time() + max(CAPTCHA_PROBE_BACKOFF, mr)
                continue
            draw_dt = time.time() - t0
            _maybe_sample_captcha(r.content, provider=provider, context="probe", draw_dt=draw_dt)

            t1 = time.time()
            try:
                _stat_inc("probe_attempt")
                captcha = recognizer.recognize(r.content)
                recog_dt = time.time() - t1
            except (RecognizerError, OperationTimeoutError, OperationFailedError) as e:
                ferr.error(e)
                _stat_inc("probe_recognize_error")
                adaptive.record_attempt(provider, False, latency=time.time() - t1, h_latency=None)
                next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
                continue

            t2 = time.time()
            r = client.get_Validate(username, captcha.code)
            val_dt = time.time() - t2

            try:
                res = r.json().get("valid")
            except Exception:
                # Likely not in operation time; backoff to avoid spamming.
                _stat_inc("probe_validate_parse_error")
                next_probe_at = time.time() + CAPTCHA_PROBE_BACKOFF
                continue

            if res == "2":
                _stat_inc("probe_success")
                adaptive.record_attempt(provider, True, latency=recog_dt, h_latency=draw_dt + val_dt)
            elif res == "0":
                _stat_inc("probe_fail")
                adaptive.record_attempt(provider, False, latency=recog_dt, h_latency=draw_dt + val_dt)
            else:
                # Unknown response, skip stats.
                _stat_inc("probe_validate_unknown")
                pass

            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
        except Exception as e:
            ferr.error(e)
            _stat_inc("probe_error")
            next_probe_at = time.time() + (_get_probe_interval() or CAPTCHA_PROBE_INTERVAL)
        finally:
            if client is not None:
                _return_client(probePool, client, "probePool")


def _dump_respose_content(content, filename):
    path = os.path.join(_USER_WEB_LOG_DIR, filename)
    with open(path, "wb") as fp:
        fp.write(content)


def _safe_parse_supply_cancel(r, context):
    try:
        tables = get_tables(r._tree)
        if len(tables) < 2:
            raise UnexceptedHTMLFormat(
                msg="missing datagrid tables (%s), tables=%d" % (context, len(tables))
            )
        elected = get_courses(tables[1])
        plans = get_courses_with_detail(tables[0])
        _record_html_parse_success()
        return elected, plans, True
    except Exception as e:
        ferr.error(e)
        _stat_inc("html_parse_error")
        _record_html_parse_error(context, count_stat=False)
        try:
            _add_error(
                UnexceptedHTMLFormat(
                    msg="parse failed (%s): %s" % (context, e.__class__.__name__)
                )
            )
        except Exception:
            pass
        try:
            filename = "elective.parse_fail_%s_%d.html" % (
                context.replace("/", "_"),
                int(time.time() * 1000),
            )
            _dump_respose_content(r.content, filename)
            cout.warning("HTML parse failed (%s), dump %s" % (context, filename))
        except Exception:
            pass
        return [], [], False


def _safe_put(queue, item, name):
    if item is None:
        return
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.put(item, timeout=1)
        except Exception as e:
            ferr.error(e)
            _stat_inc("queue_full_drop")
            cout.warning("Queue %s is full, drop client %s" % (name, getattr(item, "id", "?")))


def run_iaaa_loop():
    global _iaaa_consecutive_errors
    elective = None

    while True:
        iaaa_error = False
        iaaa_network_error = False
        _maybe_cooldown_sleep()
        if _offline_tick():
            continue
        if elective is None:
            elective = reloginPool.get()
            if _is_stale_client(elective):
                _stat_inc("client_stale_drop")
                elective = None
                continue
            if elective is killedElective:
                cout.info("Quit IAAA loop")
                return
        _stat_set_gauge("relogin_pool_qsize", reloginPool.qsize())
        _stat_set_gauge("iaaa_consecutive_errors", _iaaa_consecutive_errors)

        environ.iaaa_loop += 1
        _maybe_report_error_agg()
        user_agent = random.choice(USER_AGENT_LIST)

        cout.info("Try to login IAAA (client: %s)" % elective.id)
        cout.info("User-Agent: %s" % user_agent)

        try:
            iaaa = IAAAClient(timeout=iaaa_client_timeout)  # not reusable
            iaaa.set_user_agent(user_agent)

            # request elective's home page to get cookies
            r = iaaa.oauth_home()

            r = iaaa.oauth_login(username, password)

            try:
                token = r.json()["token"]
            except Exception as e:
                ferr.error(e)
                raise OperationFailedError(
                    msg="Unable to parse IAAA token. response body: %s" % r.content
                )

            elective.clear_cookies()
            elective.set_user_agent(user_agent)

            r = elective.sso_login(token)

            if is_dual_degree:
                sida = get_sida(r)
                sttp = identity
                referer = r.url
                r = elective.sso_login_dual_degree(sida, sttp, referer)

            if elective_client_max_life == -1:
                elective.set_expired_time(-1)
            else:
                elective.set_expired_time(int(time.time()) + elective_client_max_life)
            cout.info(
                "Login success (client: %s, expired_time: %s)"
                % (elective.id, _format_timestamp(elective.expired_time))
            )
            cout.info("")

            if WARMUP_AFTER_LOGIN_ENABLE:
                try:
                    _get_help_schedule(elective=elective, force_refresh=True)
                except Exception as e:
                    ferr.error(e)

            _return_client_home(elective)
            elective = None
            iaaa_error = False

        except (ServerError, StatusCodeError) as e:
            ferr.error(e)
            cout.warning("ServerError/StatusCodeError encountered")
            _add_error(e)
            iaaa_error = True

        except OperationFailedError as e:
            ferr.error(e)
            cout.warning("OperationFailedError encountered")
            _add_error(e)
            iaaa_error = True

        except RequestException as e:
            ferr.error(e)
            cout.warning("RequestException encountered")
            _add_error(e)
            iaaa_error = True
            iaaa_network_error = True
            _record_network_error_detail("iaaa_network", e)

        except IAAAIncorrectPasswordError as e:
            cout.error(e)
            _add_error(e)
            iaaa_error = True
            _maybe_failure_notify(
                _iaaa_consecutive_errors,
                "IAAAIncorrectPassword x%d (cooldown %ss)" % (
                    _iaaa_consecutive_errors,
                    int(FAILURE_COOLDOWN_SECONDS),
                ),
            )

        except IAAAForbiddenError as e:
            ferr.error(e)
            _add_error(e)
            iaaa_error = True
            _reset_runtime_state("iaaa_forbidden")
            _enter_cooldown("iaaa_forbidden", CRITICAL_COOLDOWN_SECONDS)
            _maybe_failure_notify(
                _iaaa_consecutive_errors,
                "IAAAForbidden (cooldown %ss)" % int(CRITICAL_COOLDOWN_SECONDS),
            )

        except IAAAException as e:
            ferr.error(e)
            cout.warning("IAAAException encountered")
            _add_error(e)
            iaaa_error = True

        except CaughtCheatingError as e:
            ferr.critical(e)  # 严重错误
            _add_error(e)
            iaaa_error = True
            _reset_runtime_state("caught_cheating")
            _enter_cooldown("caught_cheating", CRITICAL_COOLDOWN_SECONDS)
            _maybe_failure_notify(
                _iaaa_consecutive_errors,
                "Critical: caught cheating. Cooldown %ss" % int(CRITICAL_COOLDOWN_SECONDS),
            )

        except ElectiveException as e:
            ferr.error(e)
            cout.warning("ElectiveException encountered")
            _add_error(e)
            iaaa_error = True

        except json.JSONDecodeError as e:
            ferr.error(e)
            cout.warning("JSONDecodeError encountered")
            _add_error(e)
            iaaa_error = True

        except KeyboardInterrupt as e:
            raise e

        except Exception as e:
            ferr.exception(e)
            _add_error(e)
            iaaa_error = True

        finally:
            if iaaa_error:
                _iaaa_consecutive_errors += 1
            else:
                _iaaa_consecutive_errors = 0
            if iaaa_network_error:
                pass
            else:
                _record_network_success()
            t = login_loop_interval
            if IAAA_BACKOFF_ENABLE:
                t = _compute_backoff(
                    t,
                    _iaaa_consecutive_errors,
                    IAAA_BACKOFF_THRESHOLD,
                    IAAA_BACKOFF_FACTOR,
                    IAAA_BACKOFF_MAX,
                )
            t = _apply_offline_observe_delay(t)
            cout.info("")
            cout.info("IAAA login loop sleep %s s" % t)
            cout.info("")
            time.sleep(t)


def run_elective_loop():
    global _elective_consecutive_errors, _not_in_operation_streak, _last_not_in_operation_at
    global _not_in_operation_min_refresh_dynamic, _not_in_operation_backoff_reason
    elective = None
    noWait = False

    _load_adaptive_snapshot_once()

    ## load courses

    cs = config.courses  # OrderedDict
    N = len(cs)
    cid_cix = {}  # { cid: cix }

    for ix, (cid, c) in enumerate(cs.items()):
        goals.append(c)
        cid_cix[cid] = ix

    ## load mutex

    ms = config.mutexes
    mutexes.resize((N, N), refcheck=False)
    mutex_list = [set() for _ in range(N)]

    for mid, m in ms.items():
        ixs = []
        for cid in m.cids:
            if cid not in cs:
                raise UserInputException(
                    "In 'mutex:%s', course %r is not defined" % (mid, cid)
                )
            ix = cid_cix[cid]
            ixs.append(ix)
        for ix1, ix2 in combinations(ixs, 2):
            mutexes[ix1, ix2] = mutexes[ix2, ix1] = 1
            mutex_list[ix1].add(ix2)
            mutex_list[ix2].add(ix1)

    ## load delay

    ds = config.delays
    delays.resize(N, refcheck=False)
    delays.fill(NO_DELAY)

    for did, d in ds.items():
        cid = d.cid
        if cid not in cs:
            raise UserInputException(
                "In 'delay:%s', course %r is not defined" % (did, cid)
            )
        ix = cid_cix[cid]
        delays[ix] = d.threshold

    ## setup elective pool

    for ix in range(1, elective_client_pool_size + 1):
        _safe_put(electivePool, _make_client(ix), "electivePool")
    if probePool is not None and not _probe_pool_shared:
        for ix in range(1, CAPTCHA_PROBE_POOL_SIZE + 1):
            _safe_put(probePool, _make_probe_client(ix), "probePool")

    probe_stop = threading.Event()
    probe_pause = threading.Event()
    probe_thread = None
    if CAPTCHA_PROBE_ENABLED and probePool is not None:
        probe_thread = threading.Thread(
            target=_run_captcha_probe_loop,
            args=(probe_stop, probe_pause),
            name="CaptchaProbe",
        )
        probe_thread.daemon = True
        probe_thread.start()

    ## print header

    header = "# PKU Auto-Elective Tool v%s (%s) #" % (__version__, __date__)
    line = "#" + "-" * (len(header) - 2) + "#"

    cout.info(line)
    cout.info(header)
    cout.info(line)
    cout.info("")

    line = "-" * 30

    cout.info("> User Agent")
    cout.info(line)
    cout.info("pool_size: %d" % len(USER_AGENT_LIST))
    cout.info(line)
    cout.info("")
    cout.info("> Config")
    cout.info(line)
    cout.info("is_dual_degree: %s" % is_dual_degree)
    cout.info("identity: %s" % identity)
    cout.info("refresh_interval: %s" % refresh_interval)
    cout.info("refresh_random_deviation: %s" % refresh_random_deviation)
    cout.info("supply_cancel_page: %s" % supply_cancel_page)
    cout.info("iaaa_client_timeout: %s" % iaaa_client_timeout)
    cout.info("elective_client_timeout: %s" % elective_client_timeout)
    cout.info("login_loop_interval: %s" % login_loop_interval)
    cout.info("elective_client_pool_size: %s" % elective_client_pool_size)
    cout.info("elective_client_max_life: %s" % elective_client_max_life)
    cout.info("is_print_mutex_rules: %s" % is_print_mutex_rules)
    cout.info("captcha_adaptive_enable: %s" % adaptive.enabled)
    cout.info("captcha_adaptive_update_interval: %s" % CAPTCHA_ADAPTIVE_UPDATE_INTERVAL)
    cout.info("captcha_adaptive_fail_streak_degrade: %s" % CAPTCHA_ADAPTIVE_FAIL_STREAK)
    cout.info("captcha_probe_enabled: %s" % CAPTCHA_PROBE_ENABLED)
    if probePool is None:
        cout.info("captcha_probe_pool_size: 0")
    elif _probe_pool_shared:
        cout.info("captcha_probe_pool: shared")
    else:
        cout.info("captcha_probe_pool_size: %s" % CAPTCHA_PROBE_POOL_SIZE)
    cout.info("captcha_adaptive_report_interval: %s" % CAPTCHA_ADAPTIVE_REPORT_INTERVAL)
    cout.info("captcha_sample_enable: %s" % CAPTCHA_SAMPLE_ENABLE)
    if CAPTCHA_SAMPLE_ENABLE:
        cout.info("captcha_sample_rate: %s" % CAPTCHA_SAMPLE_RATE)
        cout.info("captcha_sample_dir: %s" % CAPTCHA_SAMPLE_DIR)
    cout.info(line)
    cout.info("")

    while True:
        noWait = False
        loop_error = False
        loop_error_reason = None
        network_error = False
        not_in_operation = False
        auth_error = False
        _maybe_cooldown_sleep()
        if _offline_tick(probe_pause):
            continue

        if elective is None:
            while True:
                elective = electivePool.get()
                if _is_stale_client(elective):
                    _stat_inc("client_stale_drop")
                    elective = None
                    continue
                break

        _stat_set_gauge("elective_pool_qsize", electivePool.qsize() + 1)
        _stat_set_gauge("relogin_pool_qsize", reloginPool.qsize())
        if probePool is not None:
            _stat_set_gauge("probe_pool_qsize", probePool.qsize())
        _stat_set_gauge("elective_consecutive_errors", _elective_consecutive_errors)

        environ.elective_loop += 1
        _maybe_report_error_agg()

        cout.info("")
        cout.info("======== Loop %d ========" % environ.elective_loop)
        cout.info("")
        if CAPTCHA_ADAPTIVE_REPORT_INTERVAL and adaptive.enabled:
            if environ.elective_loop % CAPTCHA_ADAPTIVE_REPORT_INTERVAL == 0:
                _report_adaptive_state()
        if RUNTIME_STAT_REPORT_INTERVAL and environ.elective_loop % RUNTIME_STAT_REPORT_INTERVAL == 0:
            _report_runtime_stats()
        if CAPTCHA_PROBE_ENABLED and probePool is not None and not probe_stop.is_set():
            if probe_thread is None or not probe_thread.is_alive():
                cout.warning("CaptchaProbe thread not alive, restarting")
                probe_thread = threading.Thread(
                    target=_run_captcha_probe_loop,
                    args=(probe_stop, probe_pause),
                    name="CaptchaProbe",
                )
                probe_thread.daemon = True
                probe_thread.start()

        ## print current plans

        current = [c for c in goals if c not in ignored]
        if len(current) > 0:
            cout.info("> Current tasks")
            cout.info(line)
            for ix, course in enumerate(current):
                cout.info("%02d. %s" % (ix + 1, course))
            cout.info(line)
            cout.info("")

        ## print ignored course

        if len(ignored) > 0:
            cout.info("> Ignored tasks")
            cout.info(line)
            for ix, (course, reason) in enumerate(ignored.items()):
                cout.info("%02d. %s  %s" % (ix + 1, course, reason))
            cout.info(line)
            cout.info("")

        ## print mutex rules

        if np.any(mutexes):
            cout.info("> Mutex rules")
            cout.info(line)
            ixs = [(ix1, ix2) for ix1, ix2 in np.argwhere(mutexes == 1) if ix1 < ix2]
            if is_print_mutex_rules:
                for ix, (ix1, ix2) in enumerate(ixs):
                    cout.info("%02d. %s --x-- %s" % (ix + 1, goals[ix1], goals[ix2]))
            else:
                cout.info("%d mutex rules" % len(ixs))
            cout.info(line)
            cout.info("")

        ## print delay rules

        if np.any(delays != NO_DELAY):
            cout.info("> Delay rules")
            cout.info(line)
            ds = [
                (cix, threshold)
                for cix, threshold in enumerate(delays)
                if threshold != NO_DELAY
            ]
            for ix, (cix, threshold) in enumerate(ds):
                cout.info("%02d. %s --- %d" % (ix + 1, goals[cix], threshold))
            cout.info(line)
            cout.info("")

        if len(current) == 0:
            cout.info("No tasks")
            cout.info("Quit elective loop")
            try:
                probe_stop.set()
            except Exception:
                pass
            _safe_put(reloginPool, killedElective, "reloginPool")  # kill signal
            return

        ## print client info

        cout.info(
            "> Current client: %s (qsize: %s)" % (elective.id, electivePool.qsize() + 1)
        )
        cout.info(
            "> Client expired time: %s" % _format_timestamp(elective.expired_time)
        )
        cout.info("User-Agent: %s" % elective.user_agent)
        cout.info("")

        try:
            if not elective.has_logined:
                raise _ElectiveNeedsLogin  # quit this loop

            if elective.is_expired:
                try:
                    cout.info("Logout")
                    r = elective.logout()
                except Exception as e:
                    cout.warning("Logout error")
                    cout.exception(e)
                raise _ElectiveExpired  # quit this loop

            ## check supply/cancel page

            page_r = None

            if supply_cancel_page == 1:
                cout.info("Get SupplyCancel page %s" % supply_cancel_page)

                r = page_r = elective.get_SupplyCancel(username)
                elected, plans, ok = _safe_parse_supply_cancel(
                    r, "SupplyCancel_%s" % supply_cancel_page
                )
                if not ok:
                    loop_error = True
                    loop_error_reason = "html_parse"
                    continue
                plan_map = {c.to_simplified(): c for c in plans}

            else:
                #
                # 刷新非第一页的课程，第一次请求会遇到返回空页面的情况
                #
                # 模拟方法：
                # 1.先登录辅双，打开补退选第二页
                # 2.再在同一浏览器登录主修
                # 3.刷新辅双的补退选第二页可以看到
                #
                # -----------------------------------------------
                #
                # 引入 retry 逻辑以防止以为某些特殊原因无限重试
                # 正常情况下一次就能成功，但是为了应对某些偶发错误，这里设为最多尝试 3 次
                #
                retry = 3
                while True:
                    if retry == 0:
                        raise OperationFailedError(
                            msg="unable to get normal Supplement page %s"
                            % supply_cancel_page
                        )
                    try:
                        cout.info("Get Supplement page %s" % supply_cancel_page)
                        r = page_r = elective.get_supplement(
                            username, page=supply_cancel_page
                        )  # 双学位第二页
                        elected, plans, ok = _safe_parse_supply_cancel(
                            r, "Supplement_%s" % supply_cancel_page
                        )
                        if not ok:
                            cout.warning("HTML parse failed, try SupplyCancel first")
                            _ = elective.get_SupplyCancel(username)
                        else:
                            plan_map = {c.to_simplified(): c for c in plans}
                            break
                    finally:
                        retry -= 1

            ## check available courses

            cout.info("Get available courses")

            tasks = []  # [(ix, course)]
            for ix, c in enumerate(goals):
                if c in ignored:
                    continue
                elif c in elected:
                    cout.info("%s is elected, ignored" % c)
                    _ignore_course(c, "Elected")
                    for mix in mutex_list[ix]:
                        mc = goals[mix]
                        if mc in ignored:
                            continue
                        cout.info("%s is simultaneously ignored by mutex rules" % mc)
                        _ignore_course(mc, "Mutex rules")
                else:
                    c0 = plan_map.get(c)
                    if c0 is None:
                        raise UserInputException(
                            "%s is not in your course plan, please check your config."
                            % c
                        )
                    if c0.is_available():
                        delay = delays[ix]
                        if delay != NO_DELAY and c0.remaining_quota > delay:
                            cout.info(
                                "%s hasn't reached the delay threshold %d, skip"
                                % (c0, delay)
                            )
                        else:
                            tasks.append((ix, c0))
                            cout.info("%s is AVAILABLE now !" % c0)

            tasks = deque(
                [(ix, c) for ix, c in tasks if c not in ignored]
            )  # filter again and change to deque

            adaptive.set_frozen(False)
            probe_pause.clear()

            ## elect available courses

            if len(tasks) == 0:
                cout.info("No course available")
                _maybe_adaptive_reorder("idle")
                continue

            if _captcha_is_degraded() and CAPTCHA_DEGRADE_MONITOR_ONLY:
                cout.warning("Captcha degraded, monitor-only this round")
                _notify_degraded_available(tasks)
                _maybe_adaptive_reorder("degraded")
                continue

            _maybe_adaptive_reorder("active")
            adaptive.set_frozen(True)
            probe_pause.set()

            elected = []  # cache elected courses dynamically from `get_ElectSupplement`

            while len(tasks) > 0:
                ix, course = tasks.popleft()

                is_mutex = False

                # dynamically filter course by mutex rules
                for mix in mutex_list[ix]:
                    mc = goals[mix]
                    if mc in elected:  # ignore course in advanced
                        is_mutex = True
                        cout.info("%s --x-- %s" % (course, mc))
                        cout.info("%s is ignored by mutex rules in advance" % course)
                        _ignore_course(course, "Mutex rules")
                        break

                if is_mutex:
                    continue

                cout.info("Try to elect %s" % course)

                if _captcha_is_degraded() and CAPTCHA_DEGRADE_MONITOR_ONLY:
                    left = int(_captcha_degrade_until - time.time())
                    cout.warning(
                        "Captcha degraded, skip electing for %s s (course: %s)"
                        % (max(left, 0), course)
                    )
                    _notify_degraded_available([(ix, course)])
                    break

                ## validate captcha first

                validated = False
                for _ in range(RECOGNIZER_MAX_ATTEMPT):
                    provider_name = _recognizer_names[recognizer_index]
                    cout.info("Fetch a captcha")
                    t_draw = time.time()
                    r = elective.get_DrawServlet()
                    draw_dt = time.time() - t_draw
                    _maybe_sample_captcha(
                        r.content,
                        provider=provider_name,
                        context="main",
                        draw_dt=draw_dt,
                    )
                    try:
                        t_recog = time.time()
                        _stat_inc("captcha_attempt")
                        captcha = recognizer.recognize(r.content)
                        recog_dt = time.time() - t_recog
                        _stat_inc("captcha_recognize_ok")
                    except (RecognizerError, OperationTimeoutError, OperationFailedError) as e:
                        ferr.error(e)
                        _stat_inc("captcha_recognize_error")
                        adaptive.record_attempt(provider_name, False, latency=time.time() - t_recog, h_latency=None)
                        _add_error(e)
                        _record_captcha_failure()
                        if _captcha_is_degraded():
                            break
                        cout.info("Captcha recognize failed, try again")
                        continue
                    cout.info("Recognition result: %s" % captcha.code)

                    t_val = time.time()
                    r = elective.get_Validate(username, captcha.code)
                    val_dt = time.time() - t_val
                    try:
                        res = r.json()["valid"]  # 可能会返回一个错误网页
                    except Exception as e:
                        ferr.error(e)
                        _stat_inc("captcha_validate_parse_error")
                        _record_captcha_failure()
                        if _captcha_is_degraded():
                            break
                        cout.info("Captcha validate parse failed, try again")
                        continue

                    if res == "2":
                        cout.info("Validation passed")
                        _stat_inc("captcha_validate_pass")
                        adaptive.record_attempt(provider_name, True, latency=recog_dt, h_latency=draw_dt + val_dt)
                        _record_captcha_success()
                        validated = True
                        break
                    elif res == "0":
                        cout.info("Validation failed")
                        _stat_inc("captcha_validate_fail")
                        # notify.send_bark_push(msg=WECHAT_MSG[2], prefix=WECHAT_PREFIX[2])
                        cout.info("Auto error caching skipped for good")
                        cout.info("Try again")
                        adaptive.record_attempt(provider_name, False, latency=recog_dt, h_latency=draw_dt + val_dt)
                        _record_captcha_failure()
                        if _captcha_is_degraded():
                            break
                    else:
                        cout.warning("Unknown validation result: %s" % res)
                        _stat_inc("captcha_validate_unknown")
                if not validated:
                    cout.warning(
                        "Validation failed after %d attempts, skip %s for now"
                        % (RECOGNIZER_MAX_ATTEMPT, course)
                    )
                    continue

                ## try to elect

                try:
                    r = elective.get_ElectSupplement(course.href)

                except ElectionRepeatedError as e:
                    ferr.error(e)
                    cout.warning("ElectionRepeatedError encountered")
                    notify.send_bark_push(msg=WECHAT_MSG[3], prefix=WECHAT_PREFIX[3])
                    _ignore_course(course, "Repeated")
                    _add_error(e)

                except TimeConflictError as e:
                    ferr.error(e)
                    cout.warning("TimeConflictError encountered")
                    notify.send_bark_push(
                        msg=WECHAT_MSG[4] + str(course), prefix=WECHAT_PREFIX[3]
                    )
                    _ignore_course(course, "Time conflict")
                    _add_error(e)

                except ExamTimeConflictError as e:
                    ferr.error(e)
                    cout.warning("ExamTimeConflictError encountered")
                    notify.send_bark_push(
                        msg=WECHAT_MSG[5] + str(course), prefix=WECHAT_PREFIX[3]
                    )
                    _ignore_course(course, "Exam time conflict")
                    _add_error(e)

                except ElectionPermissionError as e:
                    ferr.error(e)
                    cout.warning("ElectionPermissionError encountered")
                    _ignore_course(course, "Permission required")
                    _add_error(e)

                except CreditsLimitedError as e:
                    ferr.error(e)
                    cout.warning("CreditsLimitedError encountered")
                    _ignore_course(course, "Credits limited")
                    _add_error(e)

                except MutexCourseError as e:
                    ferr.error(e)
                    cout.warning("MutexCourseError encountered")
                    _ignore_course(course, "Mutual exclusive")
                    _add_error(e)

                except MultiEnglishCourseError as e:
                    ferr.error(e)
                    cout.warning("MultiEnglishCourseError encountered")
                    _ignore_course(course, "Multi English course")
                    _add_error(e)

                except MultiPECourseError as e:
                    ferr.error(e)
                    cout.warning("MultiPECourseError encountered")
                    _ignore_course(course, "Multi PE course")
                    _add_error(e)

                except ElectionFailedError as e:
                    ferr.error(e)
                    cout.warning(
                        "ElectionFailedError encountered"
                    )  # 具体原因不明，且不能马上重试
                    _add_error(e)

                except QuotaLimitedError as e:
                    ferr.error(e)
                    _stat_inc("elect_quota_limited")
                    # Normal in competition: seats may be gone after refresh. Do NOT treat as critical,
                    # and do not poison global error counters.
                    if course.used_quota == 0:
                        cout.warning(
                            "QuotaLimited but used_quota==0 (possible elective bug/race): %s" % course
                        )
                    else:
                        cout.info("QuotaLimited (competition): %s" % course)

                except ElectionSuccess as e:
                    # 不从此处加入 ignored，而是在下回合根据教学网返回的实际选课结果来决定是否忽略
                    cout.info("%s is ELECTED !" % course)
                    notify.send_bark_push(
                        msg=WECHAT_MSG[1] + str(course), prefix=WECHAT_PREFIX[1]
                    )
                    # --------------------------------------------------------------------------
                    # Issue #25
                    # --------------------------------------------------------------------------
                    # 但是动态地更新 elected，如果同一回合内有多门课可以被选，并且根据 mutex rules，
                    # 低优先级的课和刚选上的高优先级课冲突，那么轮到低优先级的课提交选课请求的时候，
                    # 根据这个动态更新的 elected 它将会被提前地忽略（而不是留到下一循环回合的开始时才被忽略）
                    # --------------------------------------------------------------------------
                    r = e.response  # get response from error ... a bit ugly
                    try:
                        tables = get_tables(r._tree)
                        elected.clear()
                        elected.extend(get_courses(tables[1]))
                    except Exception as ex:
                        ferr.error(ex)
                        _stat_inc("html_parse_error")

                except RuntimeError as e:
                    ferr.critical(e)
                    ferr.critical(
                        "RuntimeError with Course(name=%r, class_no=%d, school=%r, status=%s, href=%r)"
                        % (
                            course.name,
                            course.class_no,
                            course.school,
                            course.status,
                            course.href,
                        )
                    )
                    # use this private function of 'hook.py' to dump the response from `get_SupplyCancel` or `get_supplement`
                    file = _dump_request(page_r)
                    ferr.critical(
                        "Dump response from 'get_SupplyCancel / get_supplement' to %s"
                        % file
                    )
                    continue

                except (RequestException, AutoElectiveException) as e:
                    # Let outer loop classify and recover (offline/auth/html/etc).
                    raise e

                except KeyboardInterrupt as e:
                    raise e

                except Exception as e:
                    # Unknown per-course failure: keep running but don't poison global counters.
                    ferr.exception(e)
                    continue  # don't increase error count here

        except UserInputException as e:
            cout.error(e)
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__

        except (ServerError, StatusCodeError) as e:
            ferr.error(e)
            cout.warning("ServerError/StatusCodeError encountered")
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__

        except OperationFailedError as e:
            ferr.error(e)
            cout.warning("OperationFailedError encountered")
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__

        except UnexceptedHTMLFormat as e:
            ferr.error(e)
            cout.warning("UnexceptedHTMLFormat encountered")
            _add_error(e)
            _record_html_parse_error("unexcepted_html")
            loop_error = True
            loop_error_reason = e.__class__.__name__

        except RequestException as e:
            ferr.error(e)
            cout.warning("RequestException encountered")
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__
            network_error = True
            _record_network_error_detail("elective_network", e)

        except IAAAException as e:
            ferr.error(e)
            cout.warning("IAAAException encountered")
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__

        except _ElectiveNeedsLogin as e:
            cout.info("client: %s needs Login" % elective.id)
            _return_client(reloginPool, elective, "reloginPool")
            elective = None
            noWait = True

        except _ElectiveExpired as e:
            cout.info("client: %s expired" % elective.id)
            _return_client(reloginPool, elective, "reloginPool")
            elective = None
            noWait = True

        except (
            SessionExpiredError,
            InvalidTokenError,
            NoAuthInfoError,
            SharedSessionError,
        ) as e:
            ferr.error(e)
            _add_error(e)
            _record_auth_error("elective_auth")
            auth_error = True
            cout.info("client: %s needs relogin" % elective.id)
            _return_client(reloginPool, elective, "reloginPool")
            elective = None
            noWait = True

        except CaughtCheatingError as e:
            ferr.critical(e)  # critical error !
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__
            _reset_runtime_state("caught_cheating")
            _enter_cooldown("caught_cheating", CRITICAL_COOLDOWN_SECONDS)
            _maybe_failure_notify(
                _elective_consecutive_errors,
                "Critical: caught cheating. Cooldown %ss" % int(CRITICAL_COOLDOWN_SECONDS),
            )

        except NotInOperationTimeError as e:
            # Not in supplement operation time: not a failure, just backoff.
            not_in_operation = True
            old_mr = _not_in_operation_min_refresh_dynamic
            old_reason = _not_in_operation_backoff_reason
            mr, reason = _update_not_in_operation_backoff(elective=elective)
            if reason != old_reason or mr != old_mr:
                cout.warning(
                    "Not in operation time: min_refresh=%ss (%s)" % (int(mr), reason)
                )

        except SystemException as e:
            ferr.error(e)
            cout.warning("SystemException encountered")
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__
            _maybe_failure_notify(
                _elective_consecutive_errors,
                "SystemException x%d (cooldown %ss)" % (
                    _elective_consecutive_errors,
                    int(FAILURE_COOLDOWN_SECONDS),
                ),
            )

        except OperationTimeoutError as e:
            # The system is explicitly asking us to relogin.
            ferr.error(e)
            _add_error(e)
            _record_auth_error("operation_timeout")
            auth_error = True
            cout.warning("OperationTimeoutError encountered (need relogin)")
            if elective is not None:
                cout.info("client: %s needs relogin" % elective.id)
                _return_client(reloginPool, elective, "reloginPool")
                elective = None
                noWait = True

        except TipsException as e:
            ferr.error(e)
            cout.warning("TipsException encountered")
            _add_error(e)

        except json.JSONDecodeError as e:
            ferr.error(e)
            cout.warning("JSONDecodeError encountered")
            _add_error(e)
            _record_html_parse_error("json_decode")
            loop_error = True
            loop_error_reason = e.__class__.__name__
            _maybe_failure_notify(
                _elective_consecutive_errors,
                "JSONDecodeError x%d (cooldown %ss)" % (
                    _elective_consecutive_errors,
                    int(FAILURE_COOLDOWN_SECONDS),
                ),
            )

        except KeyboardInterrupt as e:
            raise e

        except Exception as e:
            ferr.exception(e)
            _add_error(e)
            loop_error = True
            loop_error_reason = e.__class__.__name__

        finally:
            adaptive.set_frozen(False)
            if not _offline_is_active():
                probe_pause.clear()
            if elective is not None:  # change elective client
                _return_client(electivePool, elective, "electivePool")
                elective = None

            if loop_error:
                _elective_consecutive_errors += 1
                if FAILURE_COOLDOWN_SECONDS > 0 and _elective_consecutive_errors >= FAILURE_NOTIFY_THRESHOLD:
                    _enter_cooldown("consecutive_failures", FAILURE_COOLDOWN_SECONDS)
                if CLIENT_POOL_RESET_THRESHOLD > 0 and _elective_consecutive_errors >= CLIENT_POOL_RESET_THRESHOLD:
                    if not_in_operation and NOT_IN_OPERATION_SKIP_POOL_RESET:
                        _stat_inc("pool_reset_skipped_not_in_operation")
                    elif _reset_client_pool(loop_error_reason or "errors"):
                        _elective_consecutive_errors = 0
            else:
                _elective_consecutive_errors = 0

            if network_error:
                pass
            else:
                _record_network_success()

            if not_in_operation:
                _not_in_operation_streak += 1
                _last_not_in_operation_at = time.time()
                _stat_set_gauge("not_in_operation_streak", _not_in_operation_streak)
            else:
                if _not_in_operation_streak != 0:
                    _not_in_operation_streak = 0
                    _stat_set_gauge("not_in_operation_streak", 0)
                if _not_in_operation_min_refresh_dynamic != NOT_IN_OPERATION_MIN_REFRESH:
                    _not_in_operation_min_refresh_dynamic = NOT_IN_OPERATION_MIN_REFRESH
                    _not_in_operation_backoff_reason = ""
                    _stat_set_gauge("not_in_operation_min_refresh", NOT_IN_OPERATION_MIN_REFRESH)

            if auth_error:
                pass
            else:
                _record_auth_success()

            _maybe_persist_adaptive()

            if noWait:
                cout.info("")
                cout.info("======== END Loop %d ========" % environ.elective_loop)
                cout.info("")
            else:
                t = _get_refresh_interval()
                if REFRESH_BACKOFF_ENABLE:
                    t = _compute_backoff(
                        t,
                        _elective_consecutive_errors,
                        REFRESH_BACKOFF_THRESHOLD,
                        REFRESH_BACKOFF_FACTOR,
                        REFRESH_BACKOFF_MAX,
                    )
                t = _apply_offline_observe_delay(t)
                t = _apply_not_in_operation_backoff(t, not_in_operation)
                cout.info("")
                cout.info("======== END Loop %d ========" % environ.elective_loop)
                cout.info("Main loop sleep %s s" % t)
                cout.info("")
                time.sleep(t)
