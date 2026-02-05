#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
import unittest
from queue import Queue
from unittest import mock

from autoelective.captcha.captcha import Captcha
import autoelective.loop as loop


class _DummyResp:
    def __init__(self, payload=None):
        self._payload = payload or {"valid": "2"}
        self.content = b"fake"

    def json(self):
        return self._payload


class _DummyRecognizer:
    def recognize(self, raw):
        return Captcha("ABCD", None, None, None, None)


class _DummyAdaptive:
    def __init__(self, providers):
        self.providers = list(providers)

    def get_order(self):
        return list(self.providers)

    def select_probe_provider(self, provider_order):
        if not provider_order:
            return None
        return provider_order[0]

    def record_attempt(self, provider, ok, latency=None, h_latency=None):
        return None

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


class ProbeIsolationOfflineTest(unittest.TestCase):
    def test_probe_uses_shared_pool(self):
        orig = {
            "CAPTCHA_PROBE_ENABLED": loop.CAPTCHA_PROBE_ENABLED,
            "CAPTCHA_PROBE_INTERVAL": loop.CAPTCHA_PROBE_INTERVAL,
            "CAPTCHA_PROBE_BACKOFF": loop.CAPTCHA_PROBE_BACKOFF,
            "CAPTCHA_PROBE_RANDOM_DEV": loop.CAPTCHA_PROBE_RANDOM_DEV,
            "electivePool": loop.electivePool,
            "probePool": getattr(loop, "probePool", None),
            "reloginPool": loop.reloginPool,
            "_client_generation": loop._client_generation,
            "_probe_pool_shared": getattr(loop, "_probe_pool_shared", False),
        }

        loop.CAPTCHA_PROBE_ENABLED = True
        loop.CAPTCHA_PROBE_INTERVAL = 0.01
        loop.CAPTCHA_PROBE_BACKOFF = 0.01
        loop.CAPTCHA_PROBE_RANDOM_DEV = 0.0
        loop._client_generation = 0

        loop.electivePool = Queue(maxsize=2)
        loop.probePool = loop.electivePool
        loop._probe_pool_shared = True
        loop.reloginPool = Queue(maxsize=2)

        loop.electivePool.put(_DummyClient(1, loop._client_generation))
        loop.electivePool.put(_DummyClient(2, loop._client_generation))

        loop.environ.runtime_stats.clear()

        stop_event = threading.Event()
        pause_event = threading.Event()

        dummy_adaptive = _DummyAdaptive(["dummy"])

        try:
            with mock.patch.object(loop, "adaptive", new=dummy_adaptive), \
                 mock.patch.object(loop, "get_recognizer", new=lambda _n: _DummyRecognizer()), \
                 mock.patch.object(loop, "_get_probe_interval", new=lambda: 0.01):
                t = threading.Thread(target=loop._run_captcha_probe_loop, args=(stop_event, pause_event))
                t.daemon = True
                t.start()
                time.sleep(0.05)
                stop_event.set()
                t.join(timeout=2.0)

            self.assertFalse(t.is_alive(), "probe thread did not stop")
            self.assertIs(loop.probePool, loop.electivePool)
            self.assertEqual(loop.electivePool.qsize(), 2)
            self.assertGreater(loop.environ.runtime_stats.get("probe_attempt", 0), 0)
        finally:
            loop.CAPTCHA_PROBE_ENABLED = orig["CAPTCHA_PROBE_ENABLED"]
            loop.CAPTCHA_PROBE_INTERVAL = orig["CAPTCHA_PROBE_INTERVAL"]
            loop.CAPTCHA_PROBE_BACKOFF = orig["CAPTCHA_PROBE_BACKOFF"]
            loop.CAPTCHA_PROBE_RANDOM_DEV = orig["CAPTCHA_PROBE_RANDOM_DEV"]
            loop.electivePool = orig["electivePool"]
            loop.probePool = orig["probePool"]
            loop.reloginPool = orig["reloginPool"]
            loop._client_generation = orig["_client_generation"]
            loop._probe_pool_shared = orig["_probe_pool_shared"]


if __name__ == "__main__":
    unittest.main()
