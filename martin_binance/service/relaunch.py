#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Restart trade sessions saved in /last_state
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.4"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

import libtmux
import time
from martin_binance import Path, WORK_PATH, LAST_STATE_PATH

time.sleep(10)

server = libtmux.Server()
session = [s for s in server.sessions if s.name == "Trade"][0]

if session:
    for window in session.windows:
        if window.name == 'srv':
            window.attached_pane.send_keys('exchanges-wrapper-srv', enter=True)
        else:
            last_state = Path(LAST_STATE_PATH, f"{window.name.replace('-', '_').replace('/', '')}.json")
            pair = Path(WORK_PATH, f"cli_{window.name.replace('-', '_').replace('/', '')}.py")
            if pair.exists() and last_state.exists():
                window.attached_pane.send_keys(f"{pair} 1", enter=True)
        time.sleep(4)
