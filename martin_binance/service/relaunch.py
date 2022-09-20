#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Restart trade sessions saved in /last_state
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.7b7"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

import libtmux
import time
from martin_binance import Path, WORK_PATH, LAST_STATE_PATH

time.sleep(10)

server = libtmux.Server()

session = server.find_where({"session_name": "Trade"})

if session:
    for window in session.list_windows():
        window_name = window.get('window_name')
        pane = window.attached_pane
        if window_name == 'srv':
            pane.send_keys('./exch_srv.py', enter=True)
        else:
            last_state = Path(LAST_STATE_PATH, f"{window_name.replace('-', '_').replace('/', '')}.json")
            pair = Path(WORK_PATH, f"cli_{window_name.replace('-', '_').replace('/', '')}.py")
            if pair.exists() and last_state.exists():
                pane.send_keys(f"{pair} 1", enter=True)
        time.sleep(4)
