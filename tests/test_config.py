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
class TestClass(LoggableClass):
    def __init__(self):
        super().__init__(name = 'cfgtest')
# ---------------------------------------------------------------------------------------
class Test_TestConfig(base.TestCase):
    def test_config(self):
        for name, value in config.__dict__.items():
            if name.upper() != name:
                continue
            self.assertEqual(Config.Get(name), value)
            self.assertEqual(Config.Get(name.lower()), value)

    def test_attributeAccess(self):
        c = TestClass()
        for name, value in config.__dict__.items():
            if name.upper() != name:
                continue
            self.assertEqual(getattr(c, name), value)
            with self.assertRaises(AttributeError):
                print(getattr(c, name.lower()))
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()