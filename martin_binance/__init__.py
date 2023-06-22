#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Free trading system for Binance SPOT API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.1-1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
from shutil import copy

STANDALONE = True
if 'margin' in str(Path().resolve()):
    print('margin detected')
    STANDALONE = False
WORK_PATH = Path(Path.home(), ".MartinBinance")
CONFIG_PATH = Path(WORK_PATH, "config")
CONFIG_FILE = Path(CONFIG_PATH, "ms_cfg.toml")
DB_FILE = Path(WORK_PATH, "funds_rate.db")
if STANDALONE:
    LOG_PATH = Path(WORK_PATH, "log")
    LAST_STATE_PATH = Path(WORK_PATH, "last_state")
    BACKTEST_PATH = Path(WORK_PATH, "back_test")
else:
    LOG_PATH = None
    LAST_STATE_PATH = None
    BACKTEST_PATH = None


def init():
    if CONFIG_FILE.exists():
        print(f"Client config found at {CONFIG_FILE}")
    else:
        print("Can't find client config file! Creating it...")
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        if STANDALONE:
            LOG_PATH.mkdir(parents=True, exist_ok=True)
            LAST_STATE_PATH.mkdir(parents=True, exist_ok=True)
        copy(Path(Path(__file__).parent.absolute(), "ms_cfg.toml.template"), CONFIG_FILE)
        copy(Path(Path(__file__).parent.absolute(), "funds_rate.db.template"), DB_FILE)
        copy(Path(Path(__file__).parent.absolute(), "cli_0_BTCUSDT.py.template"), Path(WORK_PATH, "cli_0_BTCUSDT.py"))
        copy(Path(Path(__file__).parent.absolute(), "cli_1_BTCUSDT.py.template"), Path(WORK_PATH, "cli_1_BTCUSDT.py"))
        copy(Path(Path(__file__).parent.absolute(), "cli_2_TESTBTCTESTUSDT.py.template"),
             Path(WORK_PATH, "cli_2_TESTBTCTESTUSDT.py"))
        print(f"Before the first run, set the parameters in {CONFIG_FILE}")
        if STANDALONE:
            raise SystemExit(1)
        raise UserWarning()


if __name__ == '__main__':
    init()
