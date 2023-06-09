#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization of Trading Strategy Parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.0"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from pathlib import Path
import importlib.util
from decimal import Decimal
import optuna

from tkinter.filedialog import askopenfile
from martin_binance import BACKTEST_PATH


strategy = askopenfile(defaultextension='py',
                       title='Select a file with strategy parameters',
                       initialdir=str(BACKTEST_PATH))

spec = importlib.util.spec_from_file_location("strategy", Path(BACKTEST_PATH, strategy.name))

mbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mbs)

PARAMS_FLOAT = ['PRICE_SHIFT', 'KBB']


def try_trade(**kwargs):
    for key, value in kwargs.items():
        print(key, value)
        setattr(mbs.ex, key, value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}"))
    mbs.ex.MODE = 'S'
    mbs.ex.SAVE_DS = False
    mbs.trade()
    result = float(mbs.session_result.get('profit', 0)) + float(mbs.session_result.get('free', 0))
    return result


def objective(trial):
    params = {
        'GRID_MAX_COUNT': trial.suggest_int('GRID_MAX_COUNT', 3, 5),
        'PRICE_SHIFT': trial.suggest_float('PRICE_SHIFT', 0, 0.05, step=0.01),
        'PROFIT': trial.suggest_float('PROFIT', 0.05, 0.15, step=0.05),
        'PROFIT_MAX': trial.suggest_float('PROFIT_MAX', 0.25, 1.0, step=0.05),
        'OVER_PRICE': trial.suggest_float('OVER_PRICE', 0.1, 1, step=0.1),
        'ORDER_Q': trial.suggest_int('ORDER_Q', 6, 12),
        'MARTIN': trial.suggest_float('MARTIN', 5, 15, step=1),
        'SHIFT_GRID_DELAY': trial.suggest_int('SHIFT_GRID_DELAY', 10, 60, step=5),
        'KBB': trial.suggest_float('KBB', 1, 5, step=0.5),
        'LINEAR_GRID_K': trial.suggest_int('LINEAR_GRID_K', 0, 100, step=10),
    }
    return try_trade(**params)


study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=100)

print(f"Optimal parameters: {study.best_params} for get {study.best_value}")
