#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Skript sammelt alle Tests aus seinem Verzeichnis und führt diese aus.
"""
# --------------------------------------------------------------------------------------------------
import unittest
import os
# --------------------------------------------------------------------------------------------------
def _run():
    loader = unittest.defaultTestLoader
    suite = loader.discover(os.path.dirname(__file__), 'test_*.py')
    runner = unittest.TextTestRunner()
    runner.run(suite)
# --------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    _run()