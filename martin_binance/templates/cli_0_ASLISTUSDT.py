#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Cyclic sell assets by GRID mode
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.1.4"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

import itertools
import subprocess
import ctypes
import ctypes.util
from martin_binance import Path, WORK_PATH

ID_EXCHANGE = 0
BASE_ASSET = 'USDT'
ASSETS = ['BTC', 'ETH']

def malloc_trim(trim_type: int = 0):
    ctypes.CDLL(ctypes.util.find_library('c')).malloc_trim(trim_type)

def sell_assets():
    for asset in itertools.cycle(ASSETS):
        pair = Path(WORK_PATH, f"cli_{ID_EXCHANGE}_{asset}{BASE_ASSET}.py")
        if pair.exists():
            print(f"Launching '{pair}' to sell the asset for a limited time")
            try:
                subprocess.check_call([pair, "1"])
            except KeyboardInterrupt:
                continue
            except Exception as e:
                print(f"Return code {e}")
        else:
            print(f"Not finding '{pair}' to sell the asset, setup pair first")
            break

        malloc_trim()


if __name__ == "__main__":
    sell_assets()
