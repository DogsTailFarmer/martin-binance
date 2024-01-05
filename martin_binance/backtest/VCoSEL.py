#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visual Comparison of Session Extended Log
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.1.0"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from dash import Dash, html, dcc
import plotly.graph_objects as go
import pandas as pd

from pathlib import Path
from tkinter.filedialog import askdirectory

from martin_binance import BACKTEST_PATH

clrs = {'background': '#696969',
        'text': '#7FDBFF'}

source_path = askdirectory(title='Pick a folder for base strategy: "back_test/exchange_AAABBB/snapshot/"',
                           initialdir=str(BACKTEST_PATH))
s_sell_df: pd.DataFrame = pd.read_pickle(Path(BACKTEST_PATH, source_path, "sell.pkl"))
s_buy_df = pd.read_pickle(Path(BACKTEST_PATH, source_path, "buy.pkl"))

df_path = askdirectory(title='Pick a folder for test strategy', initialdir=str(BACKTEST_PATH))
ds_ticker = pd.read_pickle(Path(BACKTEST_PATH, df_path, "ticker.pkl"))
df_grid_sell = pd.read_pickle(Path(BACKTEST_PATH, df_path, "sell.pkl"))
df_grid_buy = pd.read_pickle(Path(BACKTEST_PATH, df_path, "buy.pkl"))

app = Dash(__name__)
fig = go.Figure()
fig.update_layout(template='seaborn')

# Test data
# noinspection PyTypeChecker
fig.add_traces(go.Scatter(x=ds_ticker.index, y=ds_ticker.values, mode='lines', line_color='brown', name='Test'))

for col in df_grid_sell.columns:
    # noinspection PyTypeChecker
    fig.add_traces(go.Scatter(x=df_grid_sell.index, y=df_grid_sell[col], mode='lines', line_color='red',
                              showlegend=False))

for col in df_grid_buy.columns:
    # noinspection PyTypeChecker
    fig.add_traces(go.Scatter(x=df_grid_buy.index, y=df_grid_buy[col], mode='lines', line_color='green',
                              showlegend=False))

# SOURCE data
# noinspection PyTypeChecker

for col in s_sell_df.columns:
    # noinspection PyTypeChecker
    fig.add_traces(go.Scatter(x=s_sell_df.index, y=s_sell_df[col], mode='lines', showlegend=False,
                              line=dict(color='indianred', width=5, dash='dot')))

for col in s_buy_df.columns:
    # noinspection PyTypeChecker
    fig.add_traces(go.Scatter(x=s_buy_df.index, y=s_buy_df[col], mode='lines', showlegend=False,
                              line=dict(color='forestgreen', width=5, dash='dot')))


fig.update_layout(xaxis_tickformat="%H:%M:%S.%L", height=700, autosize=True)

app.layout = html.Div(
    [
        html.H2(children='Back test data analyser',
                style={'textAlign': 'center', 'color': clrs['text'], 'backgroundColor': clrs['background']}),
        dcc.Graph(figure=fig)
     ]
)


if __name__ == '__main__':
    app.run_server(debug=False)
