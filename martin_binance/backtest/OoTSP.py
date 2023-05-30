#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization of Trading Strategy Parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.0b8"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
import importlib.util
from decimal import Decimal
import sys


from martin_binance import BACKTEST_PATH

spec= importlib.util.spec_from_file_location("strategy",
                                             Path(BACKTEST_PATH,
                                                  Path("BTCUSDT_SOURCE", "cli_7_BTCUSDT.py")))
mbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mbs)
params_var = sys.modules[__name__]


def try_trade(**kwargs):
    for key, value in kwargs.items():
        print(key, value)
        setattr(params_var.mbs.ex, key, value)
    mbs.trade()
    return float(mbs.session_result.get('profit', 0))

'''
import optuna

def objective(trial):
    x = trial.suggest_float('x', -10, 10)
    return (x - 2) ** 2

study = optuna.create_study()
study.optimize(objective, n_trials=100)

print(study.best_params)
'''

params = {
    'MODE': 'S',
    'PROFIT_MAX': Decimal('0.3')
}

print(try_trade(**params))
