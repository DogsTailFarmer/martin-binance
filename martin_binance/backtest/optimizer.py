#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Searches for optimal parameters for a strategy under given conditions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2024 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.1.0"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"


import importlib.util as iu
from decimal import Decimal
import optuna
import asyncio

PARAMS_FLOAT = ['KBB']
N_TRIALS = 5  # 500


async def run_optimize(*args):
    # Create subprocess
    process = await asyncio.create_subprocess_exec(
        *args,
        # stdout must a pipe to be accessible as process.stdout
        stdout=asyncio.subprocess.PIPE)
    # Wait for the subprocess to finish
    stdout, stderr = await process.communicate()
    # Return stdout
    return stdout.decode().strip()


def try_trade(mbs, **kwargs):
    for key, value in kwargs.items():
        setattr(mbs.ex, key, value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}"))
    mbs.ex.MODE = 'S'
    mbs.ex.SAVE_DS = False
    mbs.ex.LOGGING = False
    mbs.trade()
    return float(mbs.session_result.get('profit', 0)) + float(mbs.session_result.get('free', 0))


def optimize(study_name, strategy, n_trials=0, storage_name=None):
    def objective(_trial):
        params = {
            'GRID_MAX_COUNT': _trial.suggest_int('GRID_MAX_COUNT', 3, 5),
            'PRICE_SHIFT': _trial.suggest_float('PRICE_SHIFT', 0, 0.05, step=0.01),
            'PROFIT': _trial.suggest_float('PROFIT', 0.05, 0.15, step=0.05),
            'PROFIT_MAX': _trial.suggest_float('PROFIT_MAX', 0.25, 1.0, step=0.05),
            'OVER_PRICE': _trial.suggest_float('OVER_PRICE', 0.1, 1, step=0.1),
            'ORDER_Q': _trial.suggest_int('ORDER_Q', 6, 12),
            'MARTIN': _trial.suggest_float('MARTIN', 5, 15, step=1),
            'SHIFT_GRID_DELAY': _trial.suggest_int('SHIFT_GRID_DELAY', 10, 150, step=10),
            'KBB': _trial.suggest_float('KBB', 1, 5, step=0.5),
            'LINEAR_GRID_K': _trial.suggest_int('LINEAR_GRID_K', 0, 100, step=20),
        }
        return try_trade(mbs, **params)

    print(f"Importing strategy from {strategy}")

    spec = iu.spec_from_file_location("strategy", strategy)
    mbs = iu.module_from_spec(spec)
    spec.loader.exec_module(mbs)
    study = optuna.create_study(study_name=study_name, storage=storage_name, direction="maximize")
    study.optimize(objective, n_trials=n_trials or N_TRIALS)
    return study
