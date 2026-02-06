#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import unittest

from autoelective.parser import get_tree, get_tables, get_table_header
import autoelective.loop as loop


def _fixture_path(*parts):
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", *parts)


class Phase1FixturesOptionalOfflineTest(unittest.TestCase):
    def _load(self, path):
        with open(path, "rb") as fp:
            return fp.read()

    def test_helpcontroller_fixture_optional(self):
        path = _fixture_path("2026_phase1", "helpcontroller.html")
        if not os.path.isfile(path):
            raise unittest.SkipTest("missing fixture: %s" % path)
        raw = self._load(path)
        tree = get_tree(raw)
        items = loop._parse_help_schedule(tree)
        # If schedule table changes, this should fail to signal needed updates.
        self.assertTrue(items, "helpcontroller schedule parse returned empty")

    def test_supplycancel_fixture_optional(self):
        path = _fixture_path("2026_phase1", "supplycancel.html")
        if not os.path.isfile(path):
            raise unittest.SkipTest("missing fixture: %s" % path)
        raw = self._load(path)
        tree = get_tree(raw)
        tables = get_tables(tree)
        self.assertGreaterEqual(len(tables), 1)
        header = get_table_header(tables[0])
        # Ensure core columns exist; fail fast on UI changes.
        for col in ("课程名", "班号", "开课单位"):
            self.assertIn(col, header)


if __name__ == "__main__":
    unittest.main()

