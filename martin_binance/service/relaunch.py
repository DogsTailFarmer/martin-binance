#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Restart trade sessions saved in /last_state
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.1r1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

import os
import libtmux
import time

time.sleep(10)

server = libtmux.Server()

session = server.find_where({"session_name": "Trade"})

if session:
    for window in session.list_windows():
        # print(dir(window))
        window_name = window.get('window_name')
        pane = window.attached_pane
        if window_name == 'srv':
            pane.send_keys('./exch_srv.py', enter=True)
        else:
            last_state = './last_state/' + window_name.replace('-', '_').replace('/', '') + '.json'
            pair = './cli_' + window_name.replace('-', '_').replace('/', '') + '.py'
            if os.path.exists(pair) and os.path.exists(last_state):
                pair += ' 1'
                pane.send_keys(pair, enter=True)
        time.sleep(4)
