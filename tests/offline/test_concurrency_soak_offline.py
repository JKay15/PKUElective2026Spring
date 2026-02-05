#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading
import time
import unittest
from queue import Queue, Empty
from unittest import mock

from autoelective.captcha.captcha import Captcha
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self.content = b"fake"

    def json(self):
        return self._payload


class _DummyRecognizer:
    def recognize(self, raw):
        return Captcha("ABCD", None, None, None, None)


class _DummyAdaptive:
    def __init__(self, providers):
        self.providers = list(providers)
        self.attempts = 0
        self.success = 0

    def get_order(self):
        return list(self.providers)

    def select_probe_provider(self, provider_order):
        if not provider_order:
            return None
        return provider_order[0]

    def record_attempt(self, provider, ok, latency=None, h_latency=None):
        self.attempts += 1
        if ok:
            self.success += 1

    def set_frozen(self, _):
        return None

    def set_enabled(self, _):
        return None

    def update_order(self, _):
        return None


class _DummyClient:
    def __init__(self, cid, gen):
        self.id = cid
        self._gen = gen
        self.has_logined = True
        self.is_expired = False

    def get_DrawServlet(self):
        return _DummyResp()

    def get_Validate(self, username, code):
        return _DummyResp({"valid": "2"})


class ConcurrencySoakOfflineTest(unittest.TestCase):
    def test_soak_concurrency(self):
        duration = float(os.getenv("SOAK_SECONDS", "300"))
        sample_interval = float(os.getenv("SOAK_SAMPLE_INTERVAL", "0.05"))
        reset_interval = float(os.getenv("SOAK_RESET_INTERVAL", "0.2"))
        pool_size = int(os.getenv("SOAK_POOL_SIZE", "6"))

        orig = {
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
            "CAPTCHA_PROBE_INTERVAL": loop.CAPTCHA_PROBE_INTERVAL,
            "CAPTCHA_PROBE_BACKOFF": loop.CAPTCHA_PROBE_BACKOFF,
            "CAPTCHA_PROBE_RANDOM_DEV": loop.CAPTCHA_PROBE_RANDOM_DEV,
            "CLIENT_POOL_RESET_COOLDOWN": loop.CLIENT_POOL_RESET_COOLDOWN,
            "elective_client_pool_size": loop.elective_client_pool_size,
            "electivePool": loop.electivePool,
            "probePool": getattr(loop, "probePool", None),
            "reloginPool": loop.reloginPool,
            "_probe_pool_shared": getattr(loop, "_probe_pool_shared", False),
            "_captcha_degrade_until": loop._captcha_degrade_until,
            "_captcha_failure_count": loop._captcha_failure_count,
            "_client_generation": loop._client_generation,
            "_last_pool_reset_at": loop._last_pool_reset_at,
        }

        loop.CAPTCHA_PROBE_ENABLED = True
        loop.CAPTCHA_PROBE_INTERVAL = 0.05
        loop.CAPTCHA_PROBE_BACKOFF = 0.05
        loop.CAPTCHA_PROBE_RANDOM_DEV = 0.0
        loop.CLIENT_POOL_RESET_COOLDOWN = 0.0
        loop.elective_client_pool_size = pool_size
        loop._captcha_degrade_until = 0.0
        loop._captcha_failure_count = 0
        loop._client_generation = 0
        loop._last_pool_reset_at = 0.0

        loop.electivePool = Queue(maxsize=pool_size)
        loop.probePool = Queue(maxsize=pool_size)
        loop._probe_pool_shared = False
        loop.reloginPool = Queue(maxsize=pool_size)

        errors = []
        error_lock = threading.Lock()
        depth_samples = []
        depth_lock = threading.Lock()

        def _record_error(e):
            with error_lock:
                errors.append(e)

        dummy_adaptive = _DummyAdaptive(["dummy"])

        def _make_dummy_client(cid, *args, **kwargs):
            return _DummyClient(cid, loop._client_generation)

        reset_count = {"n": 0}

        orig_reset = loop._reset_client_pool

        def _counted_reset(reason, force=False):
            reset_count["n"] += 1
            return orig_reset(reason, force=force)

        def _main_worker(stop_event):
            while not stop_event.is_set():
                try:
                    client = loop.electivePool.get_nowait()
                except Empty:
                    time.sleep(0.002)
                    continue
                try:
                    _ = client.id
                except Exception as e:
                    _record_error(e)
                finally:
                    loop._return_client(loop.electivePool, client, "electivePool")
                time.sleep(0.002)

        def _reset_worker(stop_event):
            while not stop_event.is_set():
                try:
                    loop._reset_client_pool("soak_reset", force=True)
                except Exception as e:
                    _record_error(e)
                time.sleep(reset_interval)

        def _sampler(stop_event):
            while not stop_event.is_set():
                with depth_lock:
                    depth_samples.append(loop.electivePool.qsize())
                time.sleep(sample_interval)

        stop_event = threading.Event()
        pause_event = threading.Event()

        try:
            with mock.patch.object(loop, "adaptive", new=dummy_adaptive), \
                 mock.patch.object(loop, "get_recognizer", new=lambda _n: _DummyRecognizer()), \
                 mock.patch.object(loop, "_make_client", new=_make_dummy_client), \
                 mock.patch.object(loop, "_reset_client_pool", new=_counted_reset), \
                 mock.patch.object(loop, "_get_probe_interval", new=lambda: 0.05), \
                 mock.patch.object(loop.cout, "warning", new=lambda *args, **kwargs: None), \
                 mock.patch.object(loop.ferr, "error", new=lambda e: _record_error(e)):

                loop._reset_client_pool("soak_init", force=True)

                probe_t = threading.Thread(target=loop._run_captcha_probe_loop, args=(stop_event, pause_event))
                main_t = threading.Thread(target=_main_worker, args=(stop_event,))
                reset_t = threading.Thread(target=_reset_worker, args=(stop_event,))
                sample_t = threading.Thread(target=_sampler, args=(stop_event,))

                for t in (probe_t, main_t, reset_t, sample_t):
                    t.daemon = True
                    t.start()

                deadline = time.monotonic() + duration
                while time.monotonic() < deadline:
                    time.sleep(0.05)

                stop_event.set()

                for t in (probe_t, main_t, reset_t, sample_t):
                    t.join(timeout=5.0)

            self.assertFalse(probe_t.is_alive(), "probe thread did not stop")
            self.assertFalse(main_t.is_alive(), "main worker did not stop")
            self.assertFalse(reset_t.is_alive(), "reset worker did not stop")
            self.assertFalse(sample_t.is_alive(), "sampler did not stop")

            self.assertEqual(errors, [])

            # Strict assertions for soak metrics
            expected_resets = max(1, int(duration / max(reset_interval, 0.01) * 0.5))
            self.assertGreaterEqual(reset_count["n"], expected_resets)

            self.assertGreater(dummy_adaptive.attempts, 0)
            success_rate = dummy_adaptive.success / float(dummy_adaptive.attempts)
            self.assertGreaterEqual(success_rate, 0.95)

            with depth_lock:
                avg_depth = sum(depth_samples) / float(len(depth_samples) or 1)
            self.assertGreaterEqual(avg_depth, pool_size * 0.3)
            self.assertLessEqual(avg_depth, pool_size * 1.0)
        finally:
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]
            loop.CAPTCHA_PROBE_INTERVAL = orig["CAPTCHA_PROBE_INTERVAL"]
            loop.CAPTCHA_PROBE_BACKOFF = orig["CAPTCHA_PROBE_BACKOFF"]
            loop.CAPTCHA_PROBE_RANDOM_DEV = orig["CAPTCHA_PROBE_RANDOM_DEV"]
            loop.CLIENT_POOL_RESET_COOLDOWN = orig["CLIENT_POOL_RESET_COOLDOWN"]
            loop.elective_client_pool_size = orig["elective_client_pool_size"]
            loop.electivePool = orig["electivePool"]
            loop.probePool = orig["probePool"]
            loop.reloginPool = orig["reloginPool"]
            loop._probe_pool_shared = orig["_probe_pool_shared"]
            loop._captcha_degrade_until = orig["_captcha_degrade_until"]
            loop._captcha_failure_count = orig["_captcha_failure_count"]
            loop._client_generation = orig["_client_generation"]
            loop._last_pool_reset_at = orig["_last_pool_reset_at"]


if __name__ == "__main__":
    unittest.main()
