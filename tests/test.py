#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------------
# pylint: disable=E0401, E0602
from base import * # pylint: disable=W0614
import test_board
import test_controller
import test_sunrise
import test_jobtimer
import test_watchdog
# ---------------------------------------------------------------------------------------------
def test():
    test_board.test()
    test_controller.test()
    test_sunrise.test()
    test_jobtimer.test()
    test_watchdog.test()
    print ("-" * 80)
    print ("{ok} of {total} tests succeded, {fail} failed.".format(**results))
    if results['fail']:
        print ("At least one test failed.")
    else:
        print ("All tests succeeded.")
# ---------------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()