#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Config for prometheus_client
# See README.md for detail
####################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.0.4b2"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'

from datetime import datetime

import os
import time
import sqlite3
import psutil
from requests import Session
import toml
import platform
from prometheus_client import start_http_server, Gauge

from martin_binance import Path, CONFIG_FILE, DB_FILE
from exchanges_wrapper import CONFIG_FILE as SRV_CONFIG_FILE

# region Import parameters

if not CONFIG_FILE.exists():
    if platform.system() == 'Darwin':
        user = (lambda: os.environ["USERNAME"] if "C:" in os.getcwd() else os.environ["USER"])()
        WORK_PATH = Path("Users", user, ".margin")
    else:
        WORK_PATH = Path().resolve()
    CONFIG_FILE = Path(WORK_PATH, "ms_cfg.toml")
    SRV_CONFIG_FILE = Path(WORK_PATH, "exch_srv_cfg.toml")
    DB_FILE = Path(WORK_PATH, "funds_rate.db")

config = toml.load(str(CONFIG_FILE)).get('Exporter')
accounts = toml.load(str(SRV_CONFIG_FILE)).get('accounts')

names = {acc['name']: acc['exchange'] for acc in accounts}
# external port for prometheus
PORT = config.get('port')

# sec delay for .db polling
SLEEP_TIME_S = config.get('sleep_time_s')

# Server name
VPS_NAME = config.get('vps_name')

# CoinMarketCap
URL = config.get('url')
API = config.get('api')
request_delay = 60 / config.get('rate_limit')

#  endregion

CURRENCY_RATE_LAST_TIME = int(time.time())

# region Metric declare
STATUS_ALARM = Gauge("margin_alarm", "1 when not order", ['exchange', 'pair', 'vps_name'])
REQUEST_DELAY_G = Gauge("request_delay_g", "request delay in sec", ['vps_name'])

SUM_F_PROFIT = Gauge("margin_f_profit", "first profit", ['exchange', 'pair', 'vps_name'])
SUM_S_PROFIT = Gauge("margin_s_profit", "second profit", ['exchange', 'pair', 'vps_name'])
LAST_RATE = Gauge("margin_last_rate", "pair last rate", ['exchange', 'pair', 'vps_name'])
LAST_RATE_USD = Gauge("margin_last_rate_usd", "last rate second coin to USD", ['exchange', 'pair', 'vps_name'])
SUM_PROFIT = Gauge("margin_sum_profit", "sum profit on last rate", ['exchange', 'pair', 'vps_name'])
SUM_PROFIT_USD = Gauge("margin_sum_profit_usd", "sum profit on last rate on USD", ['exchange', 'pair', 'vps_name'])

CYCLE_COUNT = Gauge("margin_cycle_count", "cycle count", ['exchange', 'pair', 'vps_name'])
BUY_COUNT = Gauge("margin_buy_count", "cycle buy count", ['exchange', 'pair', 'vps_name'])
SELL_COUNT = Gauge("margin_sell_count", "cycle sell count", ['exchange', 'pair', 'vps_name'])
BUY_TIME = Gauge("margin_buy_time", "cycle buy time", ['exchange', 'pair', 'vps_name'])
SELL_TIME = Gauge("margin_sell_time", "cycle sell time", ['exchange', 'pair', 'vps_name'])

BUY_INTEREST = Gauge("margin_buy_interest", "sum buy interest", ['exchange', 'pair', 'vps_name'])
SELL_INTEREST = Gauge("margin_sell_interest", "sum sell interest", ['exchange', 'pair', 'vps_name'])

F_BALANCE = Gauge("margin_f_balance", "first balance amount", ['exchange', 'pair', 'vps_name'])
S_BALANCE = Gauge("margin_s_balance", "second balance amount", ['exchange', 'pair', 'vps_name'])
TOTAL_BALANCE = Gauge("margin_balance", "total balance amount by last rate", ['exchange', 'pair', 'vps_name'])

BALANCE_USD = Gauge("margin_balance_usd", "balance amount in USD", ['name', 'exchange', 'currency', 'vps_name'])

# VPS control
VPS_CPU = Gauge("margin_vps_cpu", "average cpu load", ['vps_name'])
VPS_MEMORY = Gauge("margin_vps_memory", "average memory use in %", ['vps_name'])

# Cycle parameters
CYCLE_BUY = Gauge("margin_cycle_buy", "cycle buy", ['exchange', 'pair', 'vps_name'])
OVER_PRICE = Gauge("margin_over_price", "over price", ['exchange', 'pair', 'vps_name'])
F_DEPO = Gauge("margin_f_depo", "first depo", ['exchange', 'pair', 'vps_name'])
S_DEPO = Gauge("margin_s_depo", "second depo", ['exchange', 'pair', 'vps_name'])

''' Cycle parameters for future use
PRICE_SHIFT = Gauge("margin_price_shift", "price shift", ['exchange', 'pair'])
PROFIT = Gauge("margin_profit", "profit", ['exchange', 'pair'])
ORDER_Q = Gauge("margin_order_q", "order_q", ['exchange', 'pair'])
MARTIN = Gauge("margin_martin", "martin", ['exchange', 'pair'])
LINEAR_GRID_K = Gauge("margin_linear_grid_k", "linear_grid_k", ['exchange', 'pair'])
ADAPTIVE_TRADE_CONDITION = Gauge("margin_adaptive_trade_condition", "adaptive_trade_condition", ['exchange', 'pair'])
KB = Gauge("margin_kb", "bollinger band k bottom", ['exchange', 'pair'])
KT = Gauge("margin_kt", "bollinger band k top", ['exchange', 'pair'])
'''
# endregion


def get_rate(_currency_rate) -> {}:
    global request_delay
    replace = {
        'UST': 'USDT',
        'IOT': 'MIOTA',
        'LUNA': 'LUNC',
        'LUNA2': 'LUNA'
    }
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': API}
    session = Session()
    session.headers.update(headers)

    for currency in _currency_rate:
        _currency = replace.get(currency, currency)
        price = -1
        '''
        parameters = {'amount': 1, 'symbol': 'USD', 'convert': _currency}
        try:
            response = session.get(URL, params=parameters)
        except Exception as er:
            print(er)
        else:
            if response.status_code == 429:
                time.sleep(61)
                request_delay *= 1.5
                try:
                    response = session.get(URL, params=parameters)
                except Exception as er:
                    print(er)
            if response.status_code == 200:
                data = response.json()
                price = data['data'][0]['quote'][_currency]['price'] or -1
        '''
        _currency_rate[currency] = price
        # time.sleep(request_delay)
    return _currency_rate


def db_handler(sql_conn, _currency_rate, currency_rate_last_time):
    global request_delay
    cursor = sql_conn.cursor()
    # Aggregate score for pair on exchange
    cursor.execute('SELECT tex.name, tf.id_exchange,\
                    tf.f_currency, tf.s_currency,\
                    count(*) as cycle_count,\
                    sum(f_profit) as sum_f_profit,\
                    sum(s_profit) as sum_s_profit\
                    FROM t_funds as tf LEFT JOIN t_exchange tex USING(id_exchange)\
                    GROUP BY tex.name, tf.id_exchange, tf.f_currency, tf.s_currency')
    records = cursor.fetchall()
    # Get non-traded assets
    cursor.execute('SELECT tex.id_exchange, tex.name, ta.currency, ta.value\
                    FROM t_asset as ta LEFT JOIN t_exchange tex USING(id_exchange)\
                    WHERE ta.value > 0')
    assets = cursor.fetchall()
    # Create dict of used currencies
    for asset in assets:
        _currency_rate.setdefault(asset[2])
    for row in records:
        _currency_rate.setdefault(str(row[2]))
        _currency_rate.setdefault(str(row[3]))
    # Get currency rate for all currency from CoinMarketCap in relation to USD
    time_for_refresh = time.time() - currency_rate_last_time > 86400
    if None in _currency_rate.values() or time_for_refresh:
        get_rate(_currency_rate)
        currency_rate_last_time = int(time.time())
        REQUEST_DELAY_G.labels(VPS_NAME).set(request_delay)
        if request_delay > 60:
            request_delay = 60 / config.get('rate_limit')
    #
    F_BALANCE.clear()
    S_BALANCE.clear()
    TOTAL_BALANCE.clear()
    BALANCE_USD.clear()
    CYCLE_BUY.clear()
    F_DEPO.clear()
    S_DEPO.clear()
    OVER_PRICE.clear()
    #
    for row in records:
        # print(f"row: {row}")
        exchange = str(row[0])
        name = names.get(exchange)
        id_exchange = int(row[1])
        f_currency = str(row[2])
        s_currency = str(row[3])
        pair = f"{f_currency}/{s_currency}"
        cycle_count = int(row[4])
        CYCLE_COUNT.labels(exchange, pair, VPS_NAME).set(cycle_count)
        sum_f_profit = float(row[5])
        SUM_F_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_f_profit)
        sum_s_profit = float(row[6])
        SUM_S_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_s_profit)
        # Alarm
        cursor.execute('SELECT order_buy, order_sell\
                        FROM t_orders\
                        WHERE id_exchange=:id_exchange\
                        AND f_currency=:f_currency\
                        AND s_currency=:s_currency',
                       {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency})
        status_alarm = cursor.fetchone()
        alarm = 0
        if status_alarm:
            order_buy = int(status_alarm[0])
            order_sell = int(status_alarm[1])
            alarm = 0 if order_buy and order_sell else 1
        STATUS_ALARM.labels(exchange, pair, VPS_NAME).set(alarm)
        # Last rate
        cursor.execute('SELECT rate\
                        FROM t_funds\
                        WHERE id_exchange=:id_exchange\
                        AND f_currency=:f_currency\
                        AND s_currency=:s_currency\
                        ORDER BY id DESC LIMIT 1',
                       {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency})
        if last_rate_row := cursor.fetchone():
            last_rate = float(last_rate_row[0])
            LAST_RATE.labels(exchange, pair, VPS_NAME).set(last_rate)
        else:
            last_rate = 0.0
        # Sum profit
        sum_profit = sum_f_profit * last_rate + sum_s_profit
        SUM_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_profit)
        # Convert sum profit to USD by last rate
        sum_profit_usd = -1
        if _currency_rate.get(s_currency):
            try:
                sum_profit_usd = sum_profit / _currency_rate[s_currency]
                LAST_RATE_USD.labels(exchange, pair, VPS_NAME).set(_currency_rate[s_currency])
            except ZeroDivisionError:
                sum_profit_usd = -1
        SUM_PROFIT_USD.labels(exchange, pair, VPS_NAME).set(sum_profit_usd)
        # Sum interest income and cycle count, calculated by each buy and sell cycle
        cursor.execute('SELECT count(*), sum(100 * s_profit / s_depo), sum(cycle_time)\
                        FROM t_funds\
                        WHERE id_exchange=:id_exchange\
                        AND f_currency=:f_currency\
                        AND s_currency=:s_currency\
                        AND cycle_buy = 1',
                       {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency})
        cycle_buy_row = cursor.fetchone()

        cycle_buy_count = int(cycle_buy_row[0]) if cycle_buy_row[0] else 0
        cycle_buy_interest = float(cycle_buy_row[1]) if cycle_buy_row[1] else 0.0
        cycle_buy_time = float(cycle_buy_row[2]) if cycle_buy_row[2] else 0.0

        cursor.execute('SELECT count(*), sum(100 * f_profit / f_depo), sum(cycle_time)\
                        FROM t_funds\
                        WHERE id_exchange=:id_exchange\
                        AND f_currency=:f_currency\
                        AND s_currency=:s_currency\
                        AND cycle_buy = 0',
                       {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency})
        cycle_sell_row = cursor.fetchone()

        cycle_sell_count = int(cycle_sell_row[0]) if cycle_sell_row[0] else 0
        cycle_sell_interest = float(cycle_sell_row[1]) if cycle_sell_row[1] else 0.0
        cycle_sell_time = float(cycle_sell_row[2]) if cycle_sell_row[2] else 0.0

        BUY_COUNT.labels(exchange, pair, VPS_NAME).set(cycle_buy_count)
        BUY_TIME.labels(exchange, pair, VPS_NAME).set(cycle_buy_time)
        BUY_INTEREST.labels(exchange, pair, VPS_NAME).set(cycle_buy_interest)

        SELL_COUNT.labels(exchange, pair, VPS_NAME).set(cycle_sell_count)
        SELL_TIME.labels(exchange, pair, VPS_NAME).set(cycle_sell_time)
        SELL_INTEREST.labels(exchange, pair, VPS_NAME).set(cycle_sell_interest)

        # Balance amount
        cursor.execute('SELECT f_balance, s_balance, cycle_buy, f_depo, s_depo, over_price\
                        FROM t_funds\
                        WHERE id_exchange=:id_exchange\
                        AND f_currency=:f_currency\
                        AND s_currency=:s_currency\
                        AND active=1\
                        ORDER BY id DESC LIMIT 1',
                       {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency})
        if balance_row := cursor.fetchone():
            f_balance = balance_row[0]
            s_balance = balance_row[1]
            balance = f_balance * last_rate + s_balance
            F_BALANCE.labels(exchange, pair, VPS_NAME).set(f_balance)
            S_BALANCE.labels(exchange, pair, VPS_NAME).set(s_balance)
            TOTAL_BALANCE.labels(exchange, pair, VPS_NAME).set(balance)
            # Balance in USD cumulative for SPOT and Funding wallets
            f_balance_fw = 0.0
            for i, v in enumerate(assets):
                if v[0] == id_exchange and v[2] == f_currency:
                    f_balance_fw = v[3]
                    del assets[i]  # skipcq: PYL-E1138
                    break
            f_balance += f_balance_fw
            f_balance_usd = -1
            if _currency_rate.get(f_currency):
                try:
                    f_balance_usd = f_balance / _currency_rate[f_currency]
                except ZeroDivisionError:
                    f_balance_usd = -1
            s_balance_fw = 0.0
            for i, v in enumerate(assets):
                if v[0] == id_exchange and v[2] == s_currency:
                    s_balance_fw = v[3]
                    del assets[i]  # skipcq: PYL-E1138
                    break
            s_balance += s_balance_fw
            s_balance_usd = -1
            if _currency_rate.get(s_currency):
                try:
                    s_balance_usd = s_balance / _currency_rate[s_currency]
                except ZeroDivisionError:
                    s_balance_usd = -1
            # print(f"f_balance_usd: {f_balance_usd}, s_balance_usd: {s_balance_usd}")
            BALANCE_USD.labels(name, exchange, f_currency, VPS_NAME).set(f_balance_usd)
            BALANCE_USD.labels(name, exchange, s_currency, VPS_NAME).set(s_balance_usd)
            # Cycle parameters
            CYCLE_BUY.labels(exchange, pair, VPS_NAME).set(balance_row[2])
            F_DEPO.labels(exchange, pair, VPS_NAME).set(balance_row[3])
            S_DEPO.labels(exchange, pair, VPS_NAME).set(balance_row[4])
            OVER_PRICE.labels(exchange, pair, VPS_NAME).set(balance_row[5])

    for asset in assets:
        if _currency_rate.get(asset[2]):
            try:
                usd_amount = asset[3] / _currency_rate[asset[2]]
            except ZeroDivisionError:
                usd_amount = -1
            if usd_amount >= 1.0:
                BALANCE_USD.labels(names.get(asset[1]), asset[1], asset[2], VPS_NAME).set(usd_amount)

    cursor.close()
    return currency_rate_last_time


if __name__ == '__main__':
    # Start up the server to expose the metrics.
    currency_rate = {}
    start_http_server(PORT)
    sqlite_connection = None
    try:
        sqlite_connection = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    except sqlite3.Error as error:
        print("SQLite error:", error)
    while True:
        try:
            CURRENCY_RATE_LAST_TIME = db_handler(sqlite_connection, currency_rate, CURRENCY_RATE_LAST_TIME)
        except sqlite3.Error as error:
            print("DB operational error:", error)
        VPS_CPU.labels(VPS_NAME).set(100 * psutil.getloadavg()[0] / psutil.cpu_count())
        #
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        total_used_percent = 100 * float(swap.used + memory.used) / (swap.total + memory.total)
        VPS_MEMORY.labels(VPS_NAME).set(total_used_percent)
        #
        time.sleep(SLEEP_TIME_S)
