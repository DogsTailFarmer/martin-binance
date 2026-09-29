#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Perfectly Synchronized Visual Comparison of Session Log (Strict Timeline Alignment)
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "4.0.0"

from dash import Dash, html, dcc
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
from tkinter.filedialog import askdirectory
from martin_binance import BACKTEST_PATH, WORK_PATH, LAST_STATE_PATH

clrs = {'background': '#696969', 'text': '#7FDBFF'}

# ==========================================
# 1. DATA LOADING & AUTOMATIC PATH ROUTING
# ==========================================

# Select BASE strategy directory (contains snapshot subfolder)
source_root = Path(askdirectory(title='Pick ROOT folder for BASE strategy', initialdir=str(BACKTEST_PATH)))
s_snapshot = source_root / "snapshot"

# Safe loading for base strategy grids
s_sell_df = pd.read_pickle(s_snapshot / "sell.pkl") if (s_snapshot / "sell.pkl").exists() else pd.DataFrame()
s_buy_df = pd.read_pickle(s_snapshot / "buy.pkl") if (s_snapshot / "buy.pkl").exists() else pd.DataFrame()

# Select TEST strategy directory (files are stored flat in root folder)
test_folder = Path(askdirectory(title='Pick ROOT folder for TEST strategy', initialdir=str(BACKTEST_PATH)))

# Safe loading for test strategy grids
df_grid_sell = pd.read_pickle(test_folder / "sell.pkl") if (test_folder / "sell.pkl").exists() else pd.DataFrame()
df_grid_buy = pd.read_pickle(test_folder / "buy.pkl") if (test_folder / "buy.pkl").exists() else pd.DataFrame()

# Ticker is mandatory for timeline reference
ticker_path = test_folder / "ticker.pkl"
if not ticker_path.exists():
    raise FileNotFoundError(f"Critical error: mandatory ticker file not found at {ticker_path}")
raw_ticker = pd.read_pickle(ticker_path)

# Calculate strict backtest session start time boundaries
backtest_start_time = raw_ticker.index.min().floor('s')

# --- LOAD AND FILTER REAL TRADES FROM CSV ---
trades_file = Path(WORK_PATH, LAST_STATE_PATH, f"{source_root.name}.csv")
df_trades = pd.DataFrame()

if trades_file.exists() and trades_file.stat().st_size > 0:
    print(f" Loading execution logs from: {trades_file.name}")
    raw_csv_data = []
    with open(trades_file, 'r', encoding='utf-8') as f:
        for line in f:
            values = line.strip().split(',')
            if len(values) == 12 and values in ('TRADE', 'TRADE_BY_MARKET'):
                raw_csv_data.append(values)

    if raw_csv_data:
        df_temp = pd.DataFrame(raw_csv_data)
        trades_dict = {
            "time": pd.to_datetime(df_temp.iloc[:, 1].astype(float), unit='ms').dt.tz_localize(None).dt.floor('s'),
            "side": df_temp.iloc[:, 2],
            "qty": df_temp.iloc[:, 10].astype(float),
            "price": df_temp.iloc[:, 11].astype(float)
        }
        temp_trades_df = pd.DataFrame(trades_dict).set_index("time").dropna(subset=['price'])

        # --- STRICT ALIGNMENT: Crop trades to exactly match the ticker's start time ---
        df_trades = temp_trades_df[temp_trades_df.index >= backtest_start_time]
        print(
            f" Synced trades: Kept {len(df_trades)} out of {len(temp_trades_df)} total records starting from {backtest_start_time}")
else:
    print(f"⚠️ Warning: Trade log file {trades_file} not found or empty.")


# ==========================================
# 2. GRID TRACE OPTIMIZATION FUNCTION
# ==========================================
def create_fast_trace(df, color, name, dash=None, width=1):
    if df.empty:
        return None

    # Extract only rows where grid levels actually changed
    df_changes = df.ffill().pct_change().dropna(how='all')
    df_filtered = df.loc[df_changes.index].copy()

    # Downsample points linearly using simple slice step if dataframe is too heavy
    if len(df_filtered) > 2000:
        df_filtered = df_filtered.iloc[::5]

    df_filtered.index = df_filtered.index.floor('s')

    x_data, y_data = [], []
    for col in df_filtered.columns:
        x_data.extend(df_filtered.index.tolist());
        x_data.append(None)
        y_data.extend(df_filtered[col].tolist());
        y_data.append(None)

    line_layout = {'color': color, 'width': width}
    if dash: line_layout['dash'] = dash
    return go.Scatter(x=x_data, y=y_data, mode='lines', name=name, line=line_layout, showlegend=True)


# ==========================================
# 3. DATA PREPARATION & PLOTTING ENGINE
# ==========================================

# Slice every 25th element to keep raw timelines clean and remove any visual gaps
ds_ticker = raw_ticker.iloc[::25].copy()
ds_ticker.index = ds_ticker.index.floor('s')

fig = go.Figure()
fig.update_layout(template='seaborn')

# Plot Base Ticker line (Test)
fig.add_trace(go.Scatter(x=ds_ticker.index, y=ds_ticker.values, mode='lines', line_color='brown', name='Ticker (Test)'))

# Compile grid overlays safely
grid_traces = [
    create_fast_trace(df_grid_sell, 'red', 'Test Sell Grid'),
    create_fast_trace(df_grid_buy, 'green', 'Test Buy Grid'),
    create_fast_trace(s_sell_df, 'indianred', 'Source Sell Grid', dash='dot', width=2),
    create_fast_trace(s_buy_df, 'forestgreen', 'Source Buy Grid', dash='dot', width=2)
]
for trace in grid_traces:
    if trace is not None: fig.add_trace(trace)

# --- INJECT REAL TRADE MARKERS (BUY / SELL) ---
if not df_trades.empty:
    buys = df_trades[df_trades['side'].str.upper() == 'BUY']
    sells = df_trades[df_trades['side'].str.upper() == 'SELL']

    if not buys.empty:
        fig.add_trace(go.Scatter(
            x=buys.index, y=buys['price'], mode='markers', name='Actual BUY',
            marker=dict(symbol='triangle-up', size=11, color='lime', line=dict(color='black', width=1)),
            customdata=buys['qty'],
            hovertemplate='<b>BUY Execution</b><br>Price: %{y}<br>Amount: %{customdata}<br>Time: %{x}<extra></extra>'
        ))

    if not sells.empty:
        fig.add_trace(go.Scatter(
            x=sells.index, y=sells['price'], mode='markers', name='Actual SELL',
            marker=dict(symbol='triangle-down', size=11, color='crimson', line=dict(color='black', width=1)),
            customdata=sells['qty'],
            hovertemplate='<b>SELL Execution</b><br>Price: %{y}<br>Amount: %{customdata}<br>Time: %{x}<extra></extra>'
        ))

fig.update_layout(xaxis_tickformat="%H:%M:%S", height=700, autosize=True)

# ==========================================
# 4. DASH INTERFACE ROUTINES
# ==========================================
app = Dash(__name__)
app.layout = html.Div([
    html.H2(children='Perfectly Synchronized Session Analyser',
            style={'textAlign': 'center', 'color': clrs['text'], 'backgroundColor': clrs['background']}),
    dcc.Graph(figure=fig)
])

if __name__ == '__main__':
    app.run(debug=False)
