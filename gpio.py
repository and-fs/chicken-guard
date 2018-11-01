#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Enthält die GPIO-Bibliothek.
"""
import warnings

try:
    import RPi.GPIO as GPIO
except ImportError:
    from gpiomockup import GPIO

try:
    from smbus import SMBus
except ImportError:
    warnings.warn("You're currently using a SMBUS mockup!")

    class SMBus(object):
        def __init__(self, i2c_device):
            self._device = i2c_device
        def read_byte(self, bus_addr):
            return 128
        def write_byte(self, bus_addr, byte_value):
            return
