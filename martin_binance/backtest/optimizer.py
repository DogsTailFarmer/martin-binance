#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Searches for optimal parameters for a strategy under given conditions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2024 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.5"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"


import importlib.util as iu
import logging.handlers
import stat
import sys
from decimal import Decimal
from pathlib import Path

import optuna
import ujson as json

from martin_binance import LOG_PATH, TRIAL_PARAMS

OPTIMIZER = Path(__file__).absolute()
OPTIMIZER.chmod(OPTIMIZER.stat().st_mode | stat.S_IEXEC)
PARAMS_FLOAT = ['KBB']
STRATEGY = None


# noinspection PyUnusedLocal
def notify_exception(*args):
    pass  # Supress message from sys.excepthook


def any2str(_x) -> str:
    return f"{_x:.6f}".rstrip('0').rstrip('.')


def try_trade(mbs, skip_log, **kwargs):
    for key, value in kwargs.items():
        setattr(mbs.ex, key, value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}"))
    mbs.ex.MODE = 'S'
    mbs.ex.SAVE_DS = False
    mbs.ex.LOGGING = not skip_log
    global STRATEGY
    STRATEGY = mbs.trade(STRATEGY)
    return float(mbs.ex.SESSION_RESULT.get('profit', 0)) + float(mbs.ex.SESSION_RESULT.get('free', 0))


def optimize(study_name, cli, n_trials, storage_name=None, _prm_best=None, skip_log=True, show_progress_bar=False):
    sys.excepthook = notify_exception
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Load parameter definitions from JSON file
    with open(TRIAL_PARAMS) as f:
        param_defs = json.load(f)

    spec = iu.spec_from_file_location("strategy", cli)
    mbs = iu.module_from_spec(spec)
    spec.loader.exec_module(mbs)

    def objective(_trial):
        params = {}
        for param_name, param_props in param_defs.items():
            if param_props['type'] == 'int':
                params[param_name] = _trial.suggest_int(
                    param_name, *param_props['range'], step=param_props.get('step', 1)
                )
            elif param_props['type'] == 'float':
                params[param_name] = _trial.suggest_float(
                    param_name, *param_props['range'], step=param_props.get('step', 0.1)
                )
        return try_trade(mbs, skip_log, **params)

    # noinspection PyArgumentList
    _study = optuna.create_study(study_name=study_name, storage=storage_name, direction="maximize")

    if _prm_best:
        logger.info(f"Previous best params: {_prm_best}")
        _study.enqueue_trial(_prm_best)

    _study.optimize(objective, n_trials=n_trials, gc_after_trial=True, show_progress_bar=show_progress_bar)
    return _study


if __name__ == "__main__":
    logger = logging.getLogger('logger_S')
    logger.level = logging.INFO
    formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
    #
    fh = logging.handlers.RotatingFileHandler(Path(LOG_PATH, sys.argv[6]), maxBytes=500000, backupCount=5)
    fh.setFormatter(formatter)
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)
    #
    prm_best = json.loads(sys.argv[5])
    logger.info(f"Previous best params: {prm_best}")
    try:
        study = optimize(
            sys.argv[1],
            sys.argv[2],
            int(sys.argv[3]),
            storage_name=sys.argv[4],
            _prm_best=prm_best
        )
    except KeyboardInterrupt:
        pass  # ignore
    except Exception as ex:
        logger.info(f"optimizer: {ex}")
    else:
        new_value = round(study.best_value, ndigits=6)
        bp = {k: int(any2str(v)) if isinstance(v, int) else float(any2str(v)) for k, v in study.best_params.items()}

        logger.info(f"Optimal parameters: {bp} for get {new_value}")
        if new_value:
            logger.info(f"Importance parameters: {optuna.importance.get_param_importances(study)}")

        _value = round(study.get_trials()[0].value, ndigits=6)

        if not prm_best or new_value > _value:
            bp |= {'new_value': any2str(new_value), '_value': any2str(_value)}
            print(json.dumps(bp))
        else:
            print(json.dumps({}))
