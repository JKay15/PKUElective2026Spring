#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import unittest
from collections import defaultdict
from unittest import mock

import autoelective.cli as cli


class _FakeThread:
    def __init__(self, name, target, generation):
        self.name = name
        self.target = target
        self.generation = generation
        self.daemon = False
        self._started = False
        self._alive = True

    def start(self):
        self._started = True

    def is_alive(self):
        return self._started and self._alive

    def kill(self):
        self._alive = False


class _ThreadFactory:
    def __init__(self):
        self.threads = []
        self.counts = defaultdict(int)

    def __call__(self, target=None, name=None):
        gen = self.counts[name]
        self.counts[name] += 1
        t = _FakeThread(name=name, target=target, generation=gen)
        self.threads.append(t)
        return t


class ThreadGuardOfflineTest(unittest.TestCase):
    def test_thread_guard_restarts(self):
        factory = _ThreadFactory()
        sleep_calls = {"n": 0}

        def _fake_sleep(_):
            sleep_calls["n"] += 1
            if sleep_calls["n"] == 1:
                for t in factory.threads:
                    if t.generation == 0:
                        t.kill()
                return
            raise KeyboardInterrupt()

        class _DummyLogger:
            def __init__(self, *_args, **_kwargs):
                self.handlers = []

            def warning(self, *_args, **_kwargs):
                pass

        with mock.patch.object(cli, "Thread", new=factory), \
             mock.patch.object(cli.time, "sleep", new=_fake_sleep), \
             mock.patch("autoelective.logger.ConsoleLogger", new=_DummyLogger), \
             mock.patch.object(sys, "argv", new=["prog"]):

            cli.run()

        self.assertGreaterEqual(factory.counts.get("IAAA", 0), 2)
        self.assertGreaterEqual(factory.counts.get("Elective", 0), 2)


if __name__ == "__main__":
    unittest.main()
