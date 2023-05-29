#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization of Trading Strategy Parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.0b5"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
from martin_binance import BACKTEST_PATH

from runpy import run_path

if __name__ == '__main__':
   print(BACKTEST_PATH)

   i_run = run_path(str(Path(BACKTEST_PATH, Path("BTCUSDT_SOURCE", "cli_7_BTCUSDT.py"))))

   print(type(i_run))
   print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
   print(dir(i_run))
   print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
   print(i_run)
