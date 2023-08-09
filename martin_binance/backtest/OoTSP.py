#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization of Trading Strategy Parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.4"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"


from pathlib import Path
import importlib.util
from decimal import Decimal
import optuna
import inquirer
from inquirer.themes import GreenPassion
from martin_binance import BACKTEST_PATH


vis = optuna.visualization
ii_params = []

PARAMS_FLOAT = ['PRICE_SHIFT', 'KBB']


def try_trade(mbs, **kwargs):
    for key, value in kwargs.items():
        print(key, value)
        setattr(mbs.ex, key, value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}"))
    mbs.ex.MODE = 'S'
    mbs.ex.SAVE_DS = False
    mbs.trade()
    return float(mbs.session_result.get('profit', 0)) + float(
        mbs.session_result.get('free', 0)
    )


def main():
    def objective(_trial):
        params = {
            'GRID_MAX_COUNT': _trial.suggest_int('GRID_MAX_COUNT', 3, 5),
            'PRICE_SHIFT': _trial.suggest_float('PRICE_SHIFT', 0, 0.05, step=0.01),
            'PROFIT': _trial.suggest_float('PROFIT', 0.05, 0.15, step=0.05),
            'PROFIT_MAX': _trial.suggest_float('PROFIT_MAX', 0.25, 1.0, step=0.05),
            'OVER_PRICE': _trial.suggest_float('OVER_PRICE', 0.1, 1, step=0.1),
            'ORDER_Q': _trial.suggest_int('ORDER_Q', 6, 12),
            'MARTIN': _trial.suggest_float('MARTIN', 5, 15, step=1),
            'SHIFT_GRID_DELAY': _trial.suggest_int('SHIFT_GRID_DELAY', 10, 60, step=10),
            'KBB': _trial.suggest_float('KBB', 1, 5, step=0.5),
            'LINEAR_GRID_K': _trial.suggest_int('LINEAR_GRID_K', 0, 100, step=20),
        }
        return try_trade(mbs, **params)

    questions = [
        inquirer.List(
            "path",
            message="Select from saved: exchange_PAIR with the strategy you want to optimize",
            choices=[f.name for f in BACKTEST_PATH.iterdir() if f.is_dir() and f.name.count('_') == 1],
        ),
        inquirer.List(
            "mode",
            message="New study session or analise from saved one",
            choices=["New", "Analise saved study session"],
        ),
        inquirer.Text(
            "n_trials",
            message="Enter number of cycles, from 50 to 500",
            ignore=lambda x: x["mode"] == "Analise saved study session",
            default='150',
            validate=lambda _, c: 10 <= int(c) <= 500,
        ),
    ]

    answers = inquirer.prompt(questions, theme=GreenPassion())

    study_name = answers.get('path')  # Unique identifier of the study
    storage_name = f"sqlite:///{Path(BACKTEST_PATH, study_name, f'{study_name}.db')}"

    if answers.get('mode') == 'New':
        Path(BACKTEST_PATH, study_name, f'{study_name}.db').unlink(missing_ok=True)
        try:
            strategy = next(Path(BACKTEST_PATH, answers.get('path')).glob("cli_*.py"))
        except StopIteration:
            raise UserWarning(f"Can't find cli_*.py in {Path(BACKTEST_PATH, answers.get('path'))}")
        spec = importlib.util.spec_from_file_location("strategy", strategy)
        mbs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mbs)
        study = optuna.create_study(study_name=study_name, storage=storage_name, direction="maximize")
        study.optimize(objective, n_trials=int(answers.get('n_trials', '0')))
        print_study_result(study)
        print(f"Study instance saved to {storage_name} for later use")
    elif answers.get('mode') == 'Analise saved study session':
        study = optuna.load_study(study_name=study_name, storage=storage_name)

        while 1:
            questions = [
                inquirer.List(
                    "mode",
                    message="Make a choice",
                    choices=["Plot from saved", "Get parameters for specific trial", "Exit"],
                ),
                inquirer.Text(
                    "n_trial",
                    message="Enter the trial number",
                    ignore=lambda x: x["mode"] in ("Plot from saved", "Exit"),
                ),
            ]

            answers = inquirer.prompt(questions, theme=GreenPassion())
            if answers.get('mode') == 'Plot from saved':
                i_params = print_study_result(study)
                for index, p in enumerate(i_params.items()):
                    ii_params.append(p[0])
                    if index == 2:
                        break
                #
                try:
                    fig = vis.plot_optimization_history(study)
                    fig.show()
                    contour_plot = vis.plot_contour(study, params=ii_params)
                    contour_plot.show()
                    slice_plot = vis.plot_slice(study, params=ii_params)
                    slice_plot.show()
                except ImportError:
                    print("Can't find GUI, you can copy study instance to another environment for analyze it")
            elif answers.get('mode') == 'Get parameters for specific trial':
                trial = study.get_trials()[int(answers.get('n_trial', '0'))]
                print(trial.number)
                print(trial.state)
                print(trial.value)
                print(trial.params)
            else:
                break


def print_study_result(study):
    print(f"Optimal parameters: {study.best_params} for get {study.best_value}")
    importance_params = optuna.importance.get_param_importances(study)
    print("Evaluate parameter importance based on completed trials in the given study:")
    for p in importance_params.items():
        print(p)
    return importance_params


if __name__ == '__main__':
    main()
