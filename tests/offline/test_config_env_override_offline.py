#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import unittest

from autoelective.utils import Singleton
from autoelective.config import AutoElectiveConfig


class ConfigEnvOverrideOfflineTest(unittest.TestCase):
    def test_env_override_config_ini(self):
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".ini")
        try:
            tmp.write("[user]\nstudent_id=TEST_USER\npassword=TEST_PWD\ndual_degree=false\nidentity=bzx\n")
            tmp.flush()
            tmp.close()

            old_env = os.environ.get("AUTOELECTIVE_CONFIG_INI")
            os.environ["AUTOELECTIVE_CONFIG_INI"] = tmp.name
            # Reset singleton cache
            Singleton._inst.pop(AutoElectiveConfig, None)
            c = AutoElectiveConfig()
            self.assertEqual(c.iaaa_id, "TEST_USER")
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            if old_env is None:
                os.environ.pop("AUTOELECTIVE_CONFIG_INI", None)
            else:
                os.environ["AUTOELECTIVE_CONFIG_INI"] = old_env
            Singleton._inst.pop(AutoElectiveConfig, None)


if __name__ == "__main__":
    unittest.main()

