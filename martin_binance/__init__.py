#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Free trading system for Binance SPOT API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.13b3"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
from shutil import copy

from exchanges_wrapper.definitions import Interval

HEARTBEAT = 2  # Sec
ORDER_TIMEOUT = HEARTBEAT * 15  # Sec
KLINES_INIT = [Interval.ONE_MINUTE, Interval.FIFTY_MINUTES, Interval.ONE_HOUR]
#
WORK_PATH = Path(Path.home(), ".MartinBinance")
CONFIG_PATH = Path(WORK_PATH, "config")
CONFIG_FILE = Path(CONFIG_PATH, "ms_cfg.toml")
DB_FILE = Path(WORK_PATH, "funds_rate.db")
LOG_PATH = Path(WORK_PATH, "log")
LAST_STATE_PATH = Path(WORK_PATH, "last_state")
BACKTEST_PATH = Path(WORK_PATH, "back_test")
TRIAL_PARAMS = Path(WORK_PATH, "trial_params.json")
EQUAL_STR = "================================================================"


def init():
    if CONFIG_FILE.exists():
        print(f"Client config found at {CONFIG_FILE}")
    else:
        print("Can't find client config file! Creating it...")
        for path in [CONFIG_PATH, LOG_PATH, LAST_STATE_PATH]:
            path.mkdir(parents=True, exist_ok=True)

        templates = Path(Path(__file__).parent.absolute(), "templates")

        copy(Path(templates, "ms_cfg.toml"), CONFIG_FILE)

        files_to_copy = [
            "funds_rate.db",
            "trial_params.json",
            "cli_0_BTCUSDT.py",
            "cli_1_BTCUSDT.py",
            "cli_2_TESTBTCTESTUSDT.py",
            "cli_3_BTCUSDT.py"
        ]
        [copy(Path(templates, file_name), Path(WORK_PATH, file_name)) for file_name in files_to_copy]

        print(f"Before the first run, set the parameters in {CONFIG_FILE}")
        raise SystemExit(1)


if __name__ == '__main__':
    init()
