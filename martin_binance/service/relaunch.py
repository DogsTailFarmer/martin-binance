#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Restart trade sessions saved in /last_state
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2025 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.36"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

import libtmux
import time
from martin_binance import Path, WORK_PATH, LAST_STATE_PATH

server = libtmux.Server()

while not server.has_session("Trade") or not server.windows.filter(name='srv'):
    time.sleep(1)

time.sleep(1)
session = server.sessions.get(session_name="Trade")

for window in session.windows:
    if window.name == 'srv':
        window.active_pane.send_keys('exchanges-wrapper-srv', enter=True)
    else:
        last_state = Path(LAST_STATE_PATH, f"{window.name.replace('-', '_').replace('/', '')}.json")
        pair = Path(WORK_PATH, f"cli_{window.name.replace('-', '_').replace('/', '')}.py")
        if pair.exists() and last_state.exists():
            window.active_pane.send_keys(f"{pair} 1", enter=True)
    time.sleep(4)
