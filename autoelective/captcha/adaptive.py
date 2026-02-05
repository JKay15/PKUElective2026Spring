#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time


class _EWMA(object):
    def __init__(self, alpha, value=None):
        self._alpha = float(alpha)
        self._value = value

    @property
    def value(self):
        return self._value

    def update(self, x):
        if x is None:
            return self._value
        if self._value is None:
            self._value = float(x)
        else:
            self._value = self._alpha * float(x) + (1.0 - self._alpha) * self._value
        return self._value


class _Stats(object):
    def __init__(self, latency_alpha, h_alpha):
        self.count = 0
        self.success = 0
        self.failure = 0
        self.fail_streak = 0
        self.latency = _EWMA(latency_alpha, None)
        self.h_latency = _EWMA(h_alpha, None)
        self.last_update = 0.0

    def update(self, success, latency=None, h_latency=None):
        if success is None:
            return
        self.count += 1
        if success:
            self.success += 1
            self.fail_streak = 0
        else:
            self.failure += 1
            self.fail_streak += 1
        if latency is not None:
            self.latency.update(latency)
        if h_latency is not None:
            self.h_latency.update(h_latency)
        self.last_update = time.time()

    def p_hat(self):
        # Laplace smoothing to avoid 0/1 extremes with few samples.
        return (self.success + 1.0) / (self.count + 2.0)


class CaptchaAdaptiveManager(object):
    def __init__(
        self,
        providers,
        enabled=True,
        min_samples=10,
        epsilon=0.1,
        latency_alpha=0.2,
        h_alpha=0.2,
        h_init=None,
        update_interval=20,
        fail_streak_degrade=3,
        score_alpha=0.4,
        score_beta=0.6,
    ):
        self._lock = threading.Lock()
        self._enabled = bool(enabled)
        self._min_samples = max(1, int(min_samples))
        self._epsilon = max(0.0, float(epsilon))
        self._latency_alpha = float(latency_alpha)
        self._h_alpha = float(h_alpha)
        self._h = _EWMA(self._h_alpha, h_init if h_init is not None else None)
        self._update_interval = max(0, int(update_interval))
        self._fail_streak_degrade = max(0, int(fail_streak_degrade))
        self._score_alpha = max(0.0, float(score_alpha))
        self._score_beta = max(0.0, float(score_beta))
        self._providers = list(providers)
        self._stats = {p: _Stats(self._latency_alpha, self._h_alpha) for p in self._providers}
        self._frozen = False
        self._last_order = list(self._providers)
        self._base_order = list(self._providers)
        self._last_update_loop = None

    @property
    def enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)

    def set_frozen(self, frozen):
        with self._lock:
            self._frozen = bool(frozen)

    def is_frozen(self):
        with self._lock:
            return self._frozen

    def update_order(self, order):
        with self._lock:
            self._providers = list(order)
            for p in order:
                if p not in self._stats:
                    self._stats[p] = _Stats(self._latency_alpha, self._h_alpha)
                    self._base_order.append(p)
            self._last_order = list(order)

    def get_order(self):
        with self._lock:
            return list(self._providers)

    def h_estimate(self):
        with self._lock:
            return self._h.value

    def record_attempt(self, provider, success, latency=None, h_latency=None):
        if provider is None:
            return
        with self._lock:
            st = self._stats.get(provider)
            if st is None:
                st = _Stats(self._latency_alpha, self._h_alpha)
                self._stats[provider] = st
                if provider not in self._base_order:
                    self._base_order.append(provider)
            st.update(success, latency=latency, h_latency=h_latency)
            if h_latency is not None:
                self._h.update(h_latency)

    def _eligible_scores(self, order):
        scores = []
        for p in order:
            st = self._stats.get(p)
            if st is None or st.count < self._min_samples:
                continue
            p_hat = st.p_hat()
            t = st.latency.value
            h_t = st.h_latency.value
            if t is None:
                t = 0.0
            if h_t is None:
                h_t = self._h.value or 0.0
            score = p_hat - self._score_alpha * t - self._score_beta * h_t
            scores.append((p, score))
        return scores

    def _cold_start_active(self, order):
        for p in order:
            st = self._stats.get(p)
            if st is not None and st.count >= self._min_samples:
                return False
        return True

    def _apply_fail_streak_degrade(self, order):
        if self._fail_streak_degrade <= 0 or not order:
            return list(order), False
        head = order[0]
        st = self._stats.get(head)
        if st is None or st.fail_streak < self._fail_streak_degrade:
            return list(order), False
        new_order = list(order[1:]) + [head]
        return new_order, True

    def maybe_reorder(self, current_order, loop_count=None):
        if not self._enabled:
            return current_order, False, False
        with self._lock:
            if self._frozen:
                return current_order, False, False
            order = list(current_order)
            if self._cold_start_active(order):
                base = [p for p in self._base_order if p in order]
                base = base + [p for p in order if p not in base]
                new_order, switch_primary = self._apply_fail_streak_degrade(base)
                changed = new_order != order
                if changed and loop_count is not None:
                    self._last_update_loop = loop_count
                return new_order, switch_primary, changed
            if self._update_interval > 0 and loop_count is not None:
                if self._last_update_loop is not None and loop_count - self._last_update_loop < self._update_interval:
                    return order, False, False
            scores = self._eligible_scores(order)
            if not scores:
                return order, False, False
            score_map = {p: s for p, s in scores}
            scored_sorted = sorted(scores, key=lambda x: x[1], reverse=True)
            scored_names = [p for p, _ in scored_sorted]
            rest = [p for p in order if p not in score_map]
            new_order = scored_names + rest

            current = order[0] if order else None
            best = scored_sorted[0][0]
            switch_primary = False
            if current in score_map:
                cur_score = score_map[current]
                best_score = score_map[best]
                if best != current and best_score >= cur_score * (1.0 + self._epsilon):
                    switch_primary = True
            changed = new_order != order
            if changed and loop_count is not None:
                self._last_update_loop = loop_count
            return new_order, switch_primary, changed

    def select_probe_provider(self, current_order):
        with self._lock:
            order = list(current_order)
            if not order:
                return None
            # pick the provider with least samples, tie by order
            min_count = None
            candidates = []
            for p in order:
                st = self._stats.get(p)
                count = st.count if st else 0
                if min_count is None or count < min_count:
                    min_count = count
                    candidates = [p]
                elif count == min_count:
                    candidates.append(p)
            return candidates[0] if candidates else order[0]

    def snapshot(self):
        with self._lock:
            data = {}
            for p, st in self._stats.items():
                h_t = st.h_latency.value
                if h_t is None:
                    h_t = self._h.value
                score = None
                if st.count >= self._min_samples:
                    t = st.latency.value or 0.0
                    h_val = h_t or 0.0
                    score = st.p_hat() - self._score_alpha * t - self._score_beta * h_val
                data[p] = {
                    "count": st.count,
                    "success": st.success,
                    "failure": st.failure,
                    "fail_streak": st.fail_streak,
                    "latency": st.latency.value,
                    "h_latency": h_t,
                    "p_hat": st.p_hat(),
                    "score": score,
                }
            return {
                "providers": list(self._providers),
                "h": self._h.value,
                "stats": data,
            }

    def load_snapshot(self, snapshot):
        """
        Best-effort restore from `snapshot()` output.
        This is used for cold-start reduction across restarts.
        """
        if not snapshot or not isinstance(snapshot, dict):
            return False

        def _to_int(x, default=0):
            try:
                return int(x)
            except Exception:
                return default

        def _to_float(x):
            try:
                if x is None:
                    return None
                v = float(x)
                if v != v:  # NaN
                    return None
                if v < 0:
                    return None
                return v
            except Exception:
                return None

        with self._lock:
            h = _to_float(snapshot.get("h"))
            if h is not None:
                self._h._value = h

            # Keep current provider order (from config), but make sure stats exist.
            providers = snapshot.get("providers") or []
            for p in providers:
                if p not in self._stats:
                    self._stats[p] = _Stats(self._latency_alpha, self._h_alpha)
                if p not in self._base_order:
                    self._base_order.append(p)

            stats = snapshot.get("stats") or {}
            if isinstance(stats, dict):
                for p, st_data in stats.items():
                    if not isinstance(st_data, dict):
                        continue
                    st = self._stats.get(p)
                    if st is None:
                        st = _Stats(self._latency_alpha, self._h_alpha)
                        self._stats[p] = st
                        if p not in self._base_order:
                            self._base_order.append(p)
                    st.count = max(0, _to_int(st_data.get("count"), 0))
                    st.success = max(0, _to_int(st_data.get("success"), 0))
                    st.failure = max(0, _to_int(st_data.get("failure"), 0))
                    st.fail_streak = max(0, _to_int(st_data.get("fail_streak"), 0))
                    st.latency._value = _to_float(st_data.get("latency"))
                    st.h_latency._value = _to_float(st_data.get("h_latency"))

            return True
