#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
from urllib.parse import urlparse

from .const import ElectiveURL, IAAAURL


class TokenBucket:
    def __init__(self, rate, burst):
        self.rate = max(0.0, float(rate))
        self.capacity = max(0.0, float(burst))
        self.tokens = self.capacity
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens=1.0):
        if self.rate <= 0:
            return 0.0
        tokens = max(0.0, float(tokens))
        if tokens == 0.0:
            return 0.0
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = max(0.0, now - self.last)
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return waited
                missing = tokens - self.tokens
                wait = missing / self.rate if self.rate > 0 else 0.0
                self.tokens = 0.0
            if wait > 0:
                time.sleep(wait)
                waited += wait


_enabled = False
_global_bucket = None
_host_buckets = {}
_stat_inc = None
_stat_set = None


def set_stat_hooks(stat_inc=None, stat_set=None):
    global _stat_inc, _stat_set
    _stat_inc = stat_inc
    _stat_set = stat_set


def _stat_inc_call(key, delta=1):
    if _stat_inc is None:
        return
    try:
        _stat_inc(key, delta)
    except Exception:
        pass


def _stat_set_call(key, value):
    if _stat_set is None:
        return
    try:
        _stat_set(key, value)
    except Exception:
        pass


def configure(config):
    global _enabled, _global_bucket, _host_buckets
    _enabled = False
    _global_bucket = None
    _host_buckets = {}

    if config is None:
        return
    try:
        enabled = bool(config.rate_limit_enable)
    except Exception:
        enabled = False
    if not enabled:
        return

    def _bucket(rate, burst):
        if rate is None or rate <= 0:
            return None
        if burst is None or burst <= 0:
            burst = max(1.0, float(rate))
        return TokenBucket(rate, burst)

    _global_bucket = _bucket(config.rate_limit_global_rps, config.rate_limit_global_burst)

    elective = _bucket(config.rate_limit_elective_rps, config.rate_limit_elective_burst)
    iaaa = _bucket(config.rate_limit_iaaa_rps, config.rate_limit_iaaa_burst)
    if elective:
        _host_buckets[ElectiveURL.Host] = elective
    if iaaa:
        _host_buckets[IAAAURL.Host] = iaaa

    _enabled = True


def throttle(url):
    if not _enabled:
        return 0.0
    wait_total = 0.0
    try:
        if _global_bucket is not None:
            w = _global_bucket.consume(1.0)
            if w > 0:
                wait_total += w
        host = urlparse(url).hostname or ""
        bucket = _host_buckets.get(host)
        if bucket is not None:
            w = bucket.consume(1.0)
            if w > 0:
                wait_total += w
    finally:
        if wait_total > 0:
            _stat_inc_call("rate_limit_sleep")
            _stat_set_call("rate_limit_last_sleep", round(wait_total, 4))
    return wait_total
