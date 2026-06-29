#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Config for prometheus_client
# See README.md for detail
####################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.1.8"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'

import asyncio
import aiohttp
import aiosqlite

import os
import time
import psutil
import toml
import platform

from prometheus_client import start_http_server, Gauge

from martin_binance import Path, CONFIG_FILE, DB_FILE
from exchanges_wrapper import CONFIG_FILE as SRV_CONFIG_FILE

def load_config():
    global CONFIG_FILE, SRV_CONFIG_FILE, DB_FILE
    if not CONFIG_FILE.exists():
        if platform.system() == 'Darwin':
            user = os.environ.get("USERNAME") or os.environ.get("USER")
            work_path = Path("Users", user, ".margin")
        else:
            work_path = Path().resolve()
        CONFIG_FILE = Path(work_path, "ms_cfg.toml")
        SRV_CONFIG_FILE = Path(work_path, "exch_srv_cfg.toml")
        DB_FILE = Path(work_path, "funds_rate.db")
    return {
        'config': toml.load(str(CONFIG_FILE)).get('Exporter', {}),
        'accounts': toml.load(str(SRV_CONFIG_FILE)).get('accounts', [])
    }

# Load configs at startup
config_data = load_config()
config = config_data['config']
accounts = config_data['accounts']

names = {acc['name']: acc['exchange'] for acc in accounts}
PORT = config.get('port')
SLEEP_TIME_S = config.get('sleep_time_s')
VPS_NAME = config.get('vps_name')
URL = config.get('url')
API_KEY = config.get('api')
request_delay = 60 / config.get('rate_limit')

CURRENCY_RATE_LAST_TIME = int(time.time())
GET_RATE = True

REPLACE_MAP = {
    'UST': 'USDT',
    'IOT': 'MIOTA',
    'TESTUSDT': 'USDT',
    'TESTBTC': 'BTC',
    'TON': 'GRAM',
}

session = None
sql_conn = None

# region Metric declare
STATUS_ALARM = Gauge("margin_alarm", "1 when not order", ['exchange', 'pair', 'vps_name'])

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

# Cycle parameters
CYCLE_BUY = Gauge("margin_cycle_buy", "cycle buy", ['exchange', 'pair', 'vps_name'])
OVER_PRICE = Gauge("margin_over_price", "over price", ['exchange', 'pair', 'vps_name'])
F_DEPO = Gauge("margin_f_depo", "first depo", ['exchange', 'pair', 'vps_name'])
S_DEPO = Gauge("margin_s_depo", "second depo", ['exchange', 'pair', 'vps_name'])

# VPS control
VPS_CPU = Gauge("margin_vps_cpu", "average cpu load", ['vps_name'])
VPS_MEMORY = Gauge("margin_vps_memory", "average memory use in %", ['vps_name'])

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

async def init():
    global session, sql_conn
    session = aiohttp.ClientSession()
    sql_conn = await aiosqlite.connect(str(DB_FILE))
    start_http_server(PORT, addr='::')

async def close():
    await session.close()
    await sql_conn.close()

async def set_active():
    try:
        await sql_conn.execute('UPDATE t_funds SET active = 1 WHERE active = 0')
        await sql_conn.commit()
    except sqlite3.Error as ex:
        print(f"Update t_funds failed: {ex}")

async def get_rate(_currency_rate, tries=5):
    buffer_rate = {}
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': API_KEY}
    for currency in _currency_rate.keys():
        _currency = REPLACE_MAP.get(currency, currency)
        price = buffer_rate.get(_currency)
        if price is None and GET_RATE:
            parameters = {'amount': 1, 'symbol': 'USD', 'convert': _currency}
            price = -1
            for i in range(1, tries + 1):
                await asyncio.sleep(request_delay ** i)
                async with session.get(URL, params=parameters, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        try:
                            price = data['data'][0]['quote'][_currency]['price'] or -1
                        except KeyError:
                            pass
                        buffer_rate[_currency] = price
                        break
                    elif response.status == 429:
                        if i >= tries:
                            break
                    else:
                        break
        _currency_rate[currency] = price
    return _currency_rate

async def db_handler(_currency_rate, currency_rate_last_time):
    async with sql_conn.cursor() as cursor:
        # Aggregate score for pair on exchange
        await cursor.execute(
            'SELECT tex.name, tf.id_exchange,\
             tf.f_currency, tf.s_currency,\
             count(*) as cycle_count,\
             sum(f_profit) as sum_f_profit,\
             sum(s_profit) as sum_s_profit,\
             sum(f_profit*rate+s_profit) as sum_profit\
             FROM t_funds as tf LEFT JOIN t_exchange tex USING(id_exchange)\
             GROUP BY tex.name, tf.id_exchange, tf.f_currency, tf.s_currency'
        )
        records = await cursor.fetchall()
        # Get assets
        await cursor.execute(
            'SELECT tex.id_exchange, tex.name, ta.currency, ta.value\
             FROM t_asset as ta LEFT JOIN t_exchange tex USING(id_exchange)\
             WHERE ta.value > 0'
        )
        assets = await cursor.fetchall()
        # Create dict of used currencies
        for asset in assets:
            _currency_rate.setdefault(asset[2])
        for row in records:
            _currency_rate.setdefault(str(row[2]))
            _currency_rate.setdefault(str(row[3]))
        # Get currency rate for all currency from CoinMarketCap in relation to USD
        time_for_refresh = time.time() - currency_rate_last_time > 86400
        if None in _currency_rate.values() or time_for_refresh:
            await get_rate(_currency_rate)
            currency_rate_last_time = int(time.time())
        #
        F_BALANCE.clear()
        S_BALANCE.clear()
        TOTAL_BALANCE.clear()
        BALANCE_USD.clear()
        CYCLE_BUY.clear()
        F_DEPO.clear()
        S_DEPO.clear()
        OVER_PRICE.clear()
        BUY_TIME.clear()
        BUY_INTEREST.clear()
        SELL_TIME.clear()
        SELL_INTEREST.clear()
        #
        for row in records:
            # print(f"row: {row}")
            exchange = str(row[0])
            id_exchange = int(row[1])
            f_currency = str(row[2])
            s_currency = str(row[3])
            pair = f"{f_currency}/{s_currency}"
            CYCLE_COUNT.labels(exchange, pair, VPS_NAME).set(int(row[4]))
            # Sum profit
            sum_f_profit = float(row[5])
            SUM_F_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_f_profit)
            sum_s_profit = float(row[6])
            SUM_S_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_s_profit)
            sum_profit = float(row[7])
            SUM_PROFIT.labels(exchange, pair, VPS_NAME).set(sum_profit)
            # Alarm
            await cursor.execute(
                'SELECT order_buy, order_sell\
                 FROM t_orders\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            status_alarm = await cursor.fetchone()
            alarm = 0
            if status_alarm:
                order_buy = int(status_alarm[0])
                order_sell = int(status_alarm[1])
                alarm = 0 if order_buy and order_sell else 1
            STATUS_ALARM.labels(exchange, pair, VPS_NAME).set(alarm)
            # Last rate
            await cursor.execute(
                'SELECT rate\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 ORDER BY id DESC LIMIT 1',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            if last_rate_row := await cursor.fetchone():
                last_rate = float(last_rate_row[0])
                LAST_RATE.labels(exchange, pair, VPS_NAME).set(last_rate)
            else:
                last_rate = 0.0
            # Convert sum profit to USD by last rate
            sum_profit_usd = -1
            if _currency_rate.get(s_currency):
                try:
                    sum_profit_usd = sum_profit / _currency_rate[s_currency]
                    LAST_RATE_USD.labels(exchange, pair, VPS_NAME).set(_currency_rate[s_currency])
                except ZeroDivisionError:
                    sum_profit_usd = -1
            SUM_PROFIT_USD.labels(exchange, pair, VPS_NAME).set(sum_profit_usd)

            # Cycle count, calculated by each buy and sell cycle
            await cursor.execute(
                'SELECT count(*)\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 AND cycle_buy = 1',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            cycle_buy_row = await cursor.fetchone()
            cycle_buy_count = int(cycle_buy_row[0]) if cycle_buy_row[0] else 0
            await cursor.execute(
                'SELECT count(*)\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 AND cycle_buy = 0',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            cycle_sell_row = await cursor.fetchone()
            cycle_sell_count = int(cycle_sell_row[0]) if cycle_sell_row[0] else 0
            BUY_COUNT.labels(exchange, pair, VPS_NAME).set(cycle_buy_count)
            SELL_COUNT.labels(exchange, pair, VPS_NAME).set(cycle_sell_count)

            # Sum income interest, calculated by each buy and sell cycle
            await cursor.execute(
                'SELECT sum(100 * s_profit / s_depo), sum(cycle_time)\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 AND cycle_buy = 1\
                 AND active = 0',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            cycle_buy_row = await cursor.fetchone()
            cycle_buy_interest = float(cycle_buy_row[0]) if cycle_buy_row[0] else 0.0
            cycle_buy_time = float(cycle_buy_row[1]) if cycle_buy_row[1] else 0.0

            await cursor.execute(
                'SELECT sum(100 * f_profit / f_depo), sum(cycle_time)\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 AND cycle_buy = 0\
                 AND active = 0',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            cycle_sell_row = await cursor.fetchone()
            cycle_sell_interest = float(cycle_sell_row[0]) if cycle_sell_row[0] else 0.0
            cycle_sell_time = float(cycle_sell_row[1]) if cycle_sell_row[1] else 0.0

            BUY_TIME.labels(exchange, pair, VPS_NAME).set(cycle_buy_time)
            BUY_INTEREST.labels(exchange, pair, VPS_NAME).set(cycle_buy_interest)
            SELL_TIME.labels(exchange, pair, VPS_NAME).set(cycle_sell_time)
            SELL_INTEREST.labels(exchange, pair, VPS_NAME).set(cycle_sell_interest)

            # Balance amount
            await cursor.execute(
                'SELECT f_balance, s_balance, cycle_buy, f_depo, s_depo, over_price\
                 FROM t_funds\
                 WHERE id_exchange=:id_exchange\
                 AND f_currency=:f_currency\
                 AND s_currency=:s_currency\
                 ORDER BY id DESC LIMIT 1',
                 {'id_exchange': id_exchange, 'f_currency': f_currency, 's_currency': s_currency}
            )
            if balance_row := await cursor.fetchone():
                f_balance = balance_row[0]
                s_balance = balance_row[1]
                balance = f_balance * last_rate + s_balance
                F_BALANCE.labels(exchange, pair, VPS_NAME).set(f_balance)
                S_BALANCE.labels(exchange, pair, VPS_NAME).set(s_balance)
                TOTAL_BALANCE.labels(exchange, pair, VPS_NAME).set(balance)
                # Cycle parameters
                CYCLE_BUY.labels(exchange, pair, VPS_NAME).set(balance_row[2])
                F_DEPO.labels(exchange, pair, VPS_NAME).set(balance_row[3])
                S_DEPO.labels(exchange, pair, VPS_NAME).set(balance_row[4])
                OVER_PRICE.labels(exchange, pair, VPS_NAME).set(balance_row[5])

        for asset in assets:
            if _rate := _currency_rate.get(asset[2]):
                try:
                    usd_amount = asset[3] / _rate
                except ZeroDivisionError:
                    usd_amount = -1
                if usd_amount >= 1.0:
                    BALANCE_USD.labels(names.get(asset[1]), asset[1], asset[2], VPS_NAME).set(usd_amount)

        return currency_rate_last_time

async def main_loop():
    global CURRENCY_RATE_LAST_TIME
    currency_rate = {}
    try:
        while True:
            try:
                CURRENCY_RATE_LAST_TIME = await db_handler(currency_rate, CURRENCY_RATE_LAST_TIME)
            except Exception as e:
                print(f"db_handler error: {e}")
            else:
                await set_active()

            # Update system metrics
            load_avg = psutil.getloadavg()[0]
            cpu_count = psutil.cpu_count()
            VPS_CPU.labels(VPS_NAME).set(100 * load_avg / cpu_count)

            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            total_used_percent = 100 * float(swap.used + mem.used) / (swap.total + mem.total)
            VPS_MEMORY.labels(VPS_NAME).set(total_used_percent)

            await asyncio.sleep(SLEEP_TIME_S)
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        pass  # Not error

async def main():
    await init()
    try:
        await main_loop()
    finally:
        await close()

if __name__ == '__main__':
    asyncio.run(main())