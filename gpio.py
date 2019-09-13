#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Enthält die GPIO-Bibliothek.

Der Import erfolgt konditional, wenn ``RPi`` nicht verfügbar ist,
wird die Klasse ``GPIO`` aus dem Modul ``gpiomockup`` verwendet.

Das Gleiche gilt für den ``SMBus``, dieser wird hier als Mockup vergeben
wenn das Modul ``smbus`` nicht verfügbar ist.

Wenn die Mockups verwendet werden, wird eine entsprechende Warnung ausgegeben.
"""
# pylint: disable=W0613,W0611,C0414,C0103,C0111,R0201

import warnings

try:
    import RPi.GPIO as GPIO
except ImportError:
    from gpiomockup import GPIO

try:
    from smbus import SMBus
except ImportError:
    warnings.warn("You're currently using a SMBUS mockup!")

    class SMBus:
        def __init__(self, i2c_device):
            self._device = i2c_device
        def read_byte(self, bus_addr):
            return 128
        def write_byte(self, bus_addr, byte_value):
            return
