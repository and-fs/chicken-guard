#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
# pylint: disable=C0413, C0111, C0103
# ---------------------------------------------------------------------------------------
def _SetupPath():
    import sys
    import pathlib
    root = str(pathlib.Path(__file__).parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
_SetupPath()
# ---------------------------------------------------------------------------------------
import unittest
import base
import config
from shared import LoggableClass, Config
# ---------------------------------------------------------------------------------------
class _TestClass(LoggableClass):
    def __init__(self):
        super().__init__(name = 'cfgtest')
        self.update_called = False
        Config.RegisterUpdateHandler(self)

    def __call__(self):
        self.update_called = True
# ---------------------------------------------------------------------------------------
class Test_TestConfig(base.TestCase):
    def test_config(self):
        for name, value in config.__dict__.items():
            if name.upper() != name:
                continue
            self.assertEqual(Config.Get(name), value)
            self.assertEqual(Config.Get(name.lower()), value)

    def test_attributeAccess(self):
        c = _TestClass()
        for name, value in config.__dict__.items():
            if name.upper() != name:
                continue
            self.assertEqual(getattr(c, name), value)
            with self.assertRaises(AttributeError):
                getattr(c, name.lower())
        self.assertFalse(c.update_called, "call signal correctly initialised.")
        prev = Config.Get("DOORCHECK_INTERVAL")
        Config.Set("DOORCHECK_INTERVAL", -10)
        self.assertTrue(c.update_called, "update handler has been called")
        self.assertEqual(Config.Get("doorcheck_interval"), -10, "config value correctly set.")
        c.update_called = False
        Config.Update()
        self.assertTrue(c.update_called, "update handler has been called")
        self.assertEqual(Config.Get("doorcheck_interval"), prev, "config value correctly reloaded.")
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()