#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Free trading system for Binance SPOT API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.16-2"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
import shutil
#
import platform

print(f"Python {platform.python_version()}")
#
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
else:
    LOG_PATH = None
    LAST_STATE_PATH = None
if CONFIG_FILE.exists():
    print(f"Config found at {CONFIG_FILE}")
else:
    print("Can't find config file! Creating it...")
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    if STANDALONE:
        LOG_PATH.mkdir(parents=True, exist_ok=True)
        LAST_STATE_PATH.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(Path(__file__).parent.absolute(), "ms_cfg.toml.template"), CONFIG_FILE)
    shutil.copy(Path(Path(__file__).parent.absolute(), "funds_rate.db.template"), DB_FILE)
    shutil.copy(Path(Path(__file__).parent.absolute(), "cli_0_BTCUSDT.py.template"),
                Path(WORK_PATH, "cli_0_BTCUSDT.py"))
    shutil.copy(Path(Path(__file__).parent.absolute(), "cli_2_AAABBB.py.template"),
                Path(WORK_PATH, "cli_2_AAABBB.py"))
    print(f"Before the first run, set the parameters in {CONFIG_FILE}")
    if STANDALONE:
        raise SystemExit(1)
    raise UserWarning()

# TODO For remote control add:
#  * Balancing assets
