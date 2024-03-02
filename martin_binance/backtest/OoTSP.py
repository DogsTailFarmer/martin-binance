#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization of Trading Strategy Parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.0rc1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
from pathlib import Path
import optuna
import inquirer
from inquirer.themes import GreenPassion
from martin_binance import BACKTEST_PATH
from martin_binance.backtest.optimizer import optimize

SKIP_LOG = True

vis = optuna.visualization
ii_params = []


def main():
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
            message="Enter number of cycles, from 10 to 1000",
            ignore=lambda x: x["mode"] == "Analise saved study session",
            default='150',
            validate=lambda _, c: 10 <= int(c) <= 1000,
        ),
    ]

    answers = inquirer.prompt(questions, theme=GreenPassion())

    study_name = answers.get('path')  # Unique identifier of the study
    storage_name = f"sqlite:///{Path(BACKTEST_PATH, study_name, 'study.db')}"

    if answers.get('mode') == 'New':
        Path(BACKTEST_PATH, study_name, 'study.db').unlink(missing_ok=True)
        try:
            strategy = next(Path(BACKTEST_PATH, study_name).glob("cli_*.py"))
        except StopIteration:
            raise UserWarning(f"Can't find cli_*.py in {Path(BACKTEST_PATH, study_name)}")

        study = optimize(
            study_name,
            strategy,
            int(answers.get('n_trials', '0')),
            storage_name,
            skip_log=SKIP_LOG,
            show_progress_bar=SKIP_LOG
        )
        print_study_result(study)
        print(f"Study instance saved to {storage_name} for later use")
    elif answers.get('mode') == 'Analise saved study session':
        study = optuna.load_study(study_name=study_name, storage=storage_name)

        print(f"Best value: {study.best_value}")
        print(f"Original value: {study.get_trials()[0].value}")

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
    try:
        importance_params = optuna.importance.get_param_importances(study)
    except RuntimeError as e:
        importance_params = {}
        print(e)
    else:
        print("Evaluate parameter importance based on completed trials in the given study:")
        for p in importance_params.items():
            print(p)
    return importance_params


if __name__ == '__main__':
    main()
