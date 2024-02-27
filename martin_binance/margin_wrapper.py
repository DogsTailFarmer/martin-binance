"""
Python strategy cli_X_AAABBB.py <-> <margin_wrapper> <-> exchanges-wrapper <-> Exchanges API/WSS
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.2.0.b3"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import ast
import asyncio
import ujson as json
import orjson
import logging
import os
import time
import sqlite3
import random
import traceback
import pandas as pd
import csv
import pyarrow as pa
import pyarrow.parquet as pq
from shutil import rmtree, copy

from decimal import Decimal
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm

# noinspection PyPackageRequirements
import grpc
import jsonpickle
# noinspection PyPackageRequirements
from google.protobuf import json_format

from exchanges_wrapper import api_pb2

from martin_binance import BACKTEST_PATH, LAST_STATE_PATH, HEARTBEAT, KLINES_INIT, EQUAL_STR, ORDER_TIMEOUT
import martin_binance.params as ms
from martin_binance.strategy_base import (StrategyBase as Cls, TradingCapabilityManager, Style, FundsEntry, LogLevel,
                                          Order, PrivateTrade, OrderUpdate, Ticker, OrderBook, f2d, any2str)
from martin_binance.executor import Strategy
from martin_binance.client import Trade
from martin_binance.backtest.optimizer import run_optimize, OPTIMIZER, PARAMS_FLOAT

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [
    ('grpc.lb_policy_name', 'pick_first'),
    ('grpc.enable_retries', 0),
    ('grpc.keepalive_timeout_ms', 10000)
]

loop = asyncio.get_event_loop()
save_trade_queue = asyncio.Queue()

KLINES_LIM = 50  # Number of candles must be <= 1000
CANCEL_ALL_ORDERS = True  # Ask about cancel all active orders before start strategy and ms.LOAD_LAST_STATE = 0
TRADES_LIST_LIMIT = 50

TRY_LIMIT = 30
PYARROW_BATCH_BUFFER_SIZE = 20480  # Rows

logger = logging.getLogger('logger')

ORDER_BOOK_PRKT = "order_book.parquet"
TICKER_PRKT = "ticker.parquet"
MS_ORDER_ID = 'ms.order_id'
MS_ORDERS = 'ms.orders'

session_result = {}


async def save_asset():
    """
    Update account asset list and value in t_asset
    """
    connection_analytic = None
    while connection_analytic is None:
        connection_analytic = Cls.strategy.connection_analytic
        await asyncio.sleep(HEARTBEAT)
    delay = HEARTBEAT * 300  # 10 min
    max_use_update = 60 * 60 * 24  # 24h if the row has not been updated that the asset is not traded
    while True:
        try:
            res = await Cls.send_request(Cls.stub.FetchAccountInformation, api_pb2.OpenClientConnectionId)
        except asyncio.CancelledError:
            pass
        except Exception as _ex:
            logger.warning(f"Exception save_asset: {_ex}")
        else:
            balances = json_format.MessageToDict(res).get('balances', [])
            # Refresh actual balance
            try:
                balance_f = next(item for item in balances if item["asset"] == Cls.base_asset)
            except StopIteration:
                balance_f = {'asset': Cls.base_asset, 'free': '0.0', 'locked': '0.0'}
            try:
                balance_s = next(item for item in balances if item["asset"] == Cls.quote_asset)
            except StopIteration:
                balance_s = {'asset': Cls.base_asset, 'free': '0.0', 'locked': '0.0'}
            funds = {Cls.base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                     Cls.quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
            Cls.funds = funds
            # Get asset balances from Funding Wallet
            cursor = connection_analytic.cursor()
            try:
                cursor.execute('SELECT 1 FROM t_asset WHERE id_exchange=:id_exchange AND use=:use',
                               {'id_exchange': ms.ID_EXCHANGE, 'use': 1})
                main_active = cursor.fetchone()
                cursor.close()
            except sqlite3.Error as err:
                cursor.close()
                main_active = (2,)
                print(f"SELECT from t_asset: {err}")
            funding_wallet = []
            assets_fw = {}
            if Cls.exchange not in ('bitfinex', 'huobi'):
                try:
                    res = await Cls.send_request(Cls.stub.FetchFundingWallet, api_pb2.FetchFundingWalletRequest)
                except asyncio.CancelledError:
                    pass
                except Exception as _ex:
                    logger.warning(f"FetchFundingWallet: {_ex}")
                else:
                    funding_wallet = json_format.MessageToDict(res).get('balances', [])
                for fw in funding_wallet:
                    assets_fw[fw['asset']] = Decimal(fw['free']) + Decimal(fw['locked']) + Decimal(fw['freeze'])
            # Create list of cumulative asset without current pair, from SPOT wallet
            # and all assets from Funding wallet on Binance
            assets = {}
            for balance in balances:
                if Cls.exchange != 'bitfinex':
                    total = assets_fw.pop(balance['asset'], Decimal('0.0'))
                else:
                    total = Decimal('0.0')
                if balance['asset'] not in (Cls.base_asset, Cls.quote_asset) or ms.GRID_ONLY:
                    total += Decimal(balance['free']) + Decimal(balance['locked'])
                assets[balance['asset']] = float(total)
            cursor_analytic = connection_analytic.cursor()
            try:
                cursor_analytic.execute('SELECT id_exchange, currency, value, use, timestamp\
                                         FROM t_asset\
                                         WHERE id_exchange=:id_exchange',
                                        {'id_exchange': ms.ID_EXCHANGE})
                rows = cursor_analytic.fetchall()
                cursor_analytic.close()
            except sqlite3.Error as err:
                rows = []
                print(f"SELECT from t_asset: {err}")
            cursor = connection_analytic.cursor()
            try:
                cursor.execute('BEGIN')
                cursor.execute('DELETE\
                                FROM t_asset\
                                WHERE id_exchange=:id_exchange\
                                and use=:use',
                               {'id_exchange': ms.ID_EXCHANGE, 'use': 0})
                for row in rows:
                    if row[1] in (Cls.base_asset, Cls.quote_asset) and main_active == (1,):
                        amount = float(assets.pop(row[1], 0))
                        cursor.execute('UPDATE t_asset SET value=:value, timestamp=:timestamp, use=:use\
                                        WHERE id_exchange=:id_exchange\
                                        and currency=:currency',
                                       {'value': amount if ms.GRID_ONLY else 0, 'timestamp': int(time.time()), 'use': 1,
                                        'id_exchange': ms.ID_EXCHANGE, 'currency': row[1]})
                    elif row[3]:
                        # Check used currency from other pair for last update time
                        if time.time() - row[4] > max_use_update:
                            cursor.execute('DELETE FROM t_asset\
                                            WHERE id_exchange=:id_exchange\
                                            and currency=:currency',
                                           {'id_exchange': ms.ID_EXCHANGE, 'currency': row[1]})
                        assets.pop(row[1], None)
                if assets:
                    for key, value in assets.items():
                        use = 1 if key in (Cls.base_asset, Cls.quote_asset) else 0
                        cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                       (ms.ID_EXCHANGE, key, value, use, int(time.time())))
                if assets_fw:
                    for key, value in assets_fw.items():
                        cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                       (ms.ID_EXCHANGE, key, float(value), 0, int(time.time())))
                cursor.execute('COMMIT')
                cursor.close()
            except sqlite3.Error as err:
                cursor.execute('ROLLBACK')
                cursor.close()
                logger.warning(f"Refresh t_asset: {err}")
        await asyncio.sleep(delay)








