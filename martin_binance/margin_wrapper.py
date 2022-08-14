#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
margin.de <-> Python strategy <-> <margin_wrapper> <-> exchanges-wrapper <-> Exchanges API/WSS
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.3_2"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
from colorama import init as color_init
import simplejson as json
import logging
import math
import os
import time
from decimal import Decimal
import sqlite3

# noinspection PyPackageRequirements
import grpc
import jsonpickle
# noinspection PyPackageRequirements
from google.protobuf import json_format
from margin_strategy_sdk import *  # lgtm [py/polluting-import] skipcq: PY-W2000

from exchanges_wrapper.definitions import Interval
from exchanges_wrapper.events import OrderUpdateWrapper
from exchanges_wrapper import api_pb2, api_pb2_grpc

import executor as ms

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [('grpc.lb_policy_name', 'pick_first'),
                   ('grpc.enable_retries', 0),
                   ('grpc.keepalive_timeout_ms', 10000)]

loop = asyncio.get_event_loop()
KLINES_INIT = [Interval.ONE_MINUTE, Interval.FIFTY_MINUTES, Interval.ONE_HOUR]
KLINES_LIM = 100  # Number of candles must be <= 1000
CANCEL_ALL_ORDERS = True  # Ask about cancel all active orders before start strategy and ms.LOAD_LAST_STATE = 0
ALL_TRADES_LIST_LIMIT = 200
TRADES_LIST_LIMIT = 100
HEARTBEAT = 2  # Sec
RATE_LIMITER = HEARTBEAT * 5
ORDER_TIMEOUT = HEARTBEAT * 15  # Sec
logger = logging.getLogger('logger')
color_init()


def write_log(level: LogLevel, message: str) -> None:
    if level == LogLevel.DEBUG:
        logger.debug(message)
    elif level == LogLevel.INFO:
        logger.info(message)
    elif level == LogLevel.WARNING:
        logger.warning(message)
    elif level == LogLevel.ERROR:
        logger.error(message)
    elif level == LogLevel.CRITICAL:
        logger.critical(message)


def convert_from_minute(m: int) -> str:
    if 1 <= m < 3:
        s = '1m'
    elif 3 <= m < 5:
        s = '3m'
    elif 5 <= m < 15:
        s = '5m'
    elif 15 <= m < 30:
        s = '15m'
    elif 30 <= m < 60:
        s = '30m'
    elif 60 <= m < 120:
        s = '1h'
    elif 120 <= m < 240:
        s = '2h'
    elif 240 <= m < 360:
        s = '4h'
    elif 360 <= m < 480:
        s = '6h'
    elif 480 <= m < 720:
        s = '8h'
    elif 720 <= m < 1440:
        s = '12h'
    elif 1440 <= m < 4320:
        s = '1d'
    elif 4320 <= m < 10080:
        s = '3d'
    elif 10080 <= m < 44640:
        s = '1w'
    else:
        s = '1m'
    return s


class StrategyBase:
    exchange = str()
    symbol = str()
    stub = api_pb2_grpc.MartinStub
    client_id = int()
    strategy = None
    info_symbol = {}
    base_asset = str()
    quote_asset = str()
    ticker = {}
    funds = {}
    order_book = {}
    order_id = 0
    wait_order_id = []  # List of placed orders for time-out detect
    canceled_order_id = []  # List canceled orders  for time-out detect
    all_trades = []  # List of all (limit = ALL_TRADES_LIST_LIMIT) trades for a specific account and symbol
    trades = []  # List of trades associated with strategy (limit = TRADES_LIST_LIMIT)
    all_orders = []  # List of all open orders for symbol
    orders = []  # List orders associated with strategy
    tcm = None  # TradingCapabilityManager
    last_state = None
    get_buffered_funds_last_time = time.time()
    rate_limiter = RATE_LIMITER
    start_time_ms = int(time.time() * 1000)

    def __call__(self):
        return self

    class Klines:
        klines_series = {}
        klines_lim = int()

        def __init__(self, _interval):
            self.interval = _interval
            self.kline = []
            self.klines_series[_interval] = self.kline

        def refresh(self, _candle):
            candle = Candle(_candle)
            # print(f"refresh.interval: {self.interval}, candle: {candle.min_time}")
            new_time = candle.min_time
            last_time = self.kline[-1].min_time if self.kline else 0
            if new_time >= last_time:
                if new_time == last_time:
                    self.kline[-1] = candle
                else:
                    self.kline.append(candle)
                    if len(self.kline) > self.klines_lim:
                        del self.kline[0]
                self.klines_series[self.interval] = self.kline

        @classmethod
        def get_kline(cls, _interval) -> []:
            return cls.klines_series.get(_interval, [])

    @classmethod
    def order_exist(cls, _id) -> bool:
        return any(i.id == _id for i in cls.orders)

    @classmethod
    def all_order_exist(cls, _id) -> bool:
        return any(i.id == _id for i in cls.all_orders)

    @classmethod
    def get_trading_capability_manager(cls) -> TradingCapabilityManager:
        # print(f"get_trading_capability_manager.info_symbol: {cls.info_symbol}")
        return ms.Strategy.tcm

    @classmethod
    def get_first_currency(cls) -> str:
        return cls.info_symbol.get('baseAsset')

    @classmethod
    def get_second_currency(cls) -> str:
        return cls.info_symbol.get('quoteAsset')

    @classmethod
    def get_buffered_ticker(cls) -> Ticker:
        # print(f"get_buffered_ticker.ticker: {cls.ticker}")
        return Ticker(cls.ticker)

    @classmethod
    def get_buffered_funds(cls) -> Dict[str, FundsEntry]:
        # print(f"get_buffered_funds.funds: {cls.funds}")
        if time.time() - cls.get_buffered_funds_last_time > cls.rate_limiter:
            # noinspection PyTypeChecker
            loop.create_task(buffered_funds(cls.stub, cls.client_id, cls.symbol, cls.base_asset,
                                            cls.quote_asset, print_info=False))
            cls.get_buffered_funds_last_time = time.time()
        return {cls.base_asset: FundsEntry(cls.funds[cls.base_asset]),
                cls.quote_asset: FundsEntry(cls.funds[cls.quote_asset])}

    @classmethod
    def get_buffered_order_book(cls) -> OrderBook:
        # print(f"get_buffered_order_book.order_book: {cls.order_book}")
        return OrderBook(cls.order_book)

    @classmethod
    def get_buffered_recent_candles(cls, candle_size_in_minutes: int, number_of_candles: int = 50,
                                    include_current_building_candle: bool = False) -> List[Candle]:
        size = convert_from_minute(candle_size_in_minutes)
        kline = StrategyBase.Klines.get_kline(size)
        if len(kline) > number_of_candles+1:
            return kline[-number_of_candles-(0 if include_current_building_candle else 1):
                         None if include_current_building_candle else -1]
        return kline[:None if include_current_building_candle else -1]

    @classmethod
    def place_limit_order(cls, buy: bool, amount: float, price: float) -> int:
        cls.order_id += 1
        ms.Strategy.strategy.message_log(f"Send order id:{cls.order_id} for {'BUY' if buy else 'SELL'}"
                                         f" {amount} by {price} = {amount * price:f}", color=ms.Style.B_YELLOW)
        loop.create_task(place_limit_order_timeout(cls.order_id))
        loop.create_task(create_limit_order(cls.order_id, buy, str(amount), str(price)))
        if ms.FEE_FTX:
            time.sleep(0.15)
        return cls.order_id

    @classmethod
    def cancel_order(cls, order_id: int) -> None:
        loop.create_task(cancel_order_timeout(order_id))
        loop.create_task(cancel_order_call(order_id))

    @classmethod
    def get_buffered_completed_trades(cls, get_all_trades: bool = False) -> List[PrivateTrade]:
        if get_all_trades:
            return ms.Strategy.all_trades
        return ms.Strategy.trades

    @classmethod
    def get_buffered_open_orders(cls, get_all_orders: bool = False) -> List[Order]:
        if get_all_orders:
            return cls.all_orders
        return cls.orders


def trade_not_exist(_order_id: int, _trade_id: int) -> bool:
    return all(not(trade.order_id == _order_id and trade.id == _trade_id) for trade in ms.Strategy.trades)


def order_trades_sum(_order_id: int) -> Decimal:
    saved_filled_quantity = Decimal(0)
    for _trade in ms.Strategy.trades:
        if _trade.order_id == _order_id:
            saved_filled_quantity += Decimal(str(_trade.amount))
    return saved_filled_quantity


class PrivateTrade:
    def __init__(self, _trade: {}) -> None:
        # Amount of the trade.
        self.amount = float(_trade["qty"])
        # True, if the trade was a buy.
        self.buy = _trade.get('isBuyer', False)
        # id of the trade.
        self.id = _trade["id"]
        # id of the order that the trade belongs to.
        self.order_id = int(_trade["orderId"])
        # Price at which the trade was executed.
        self.price = float(_trade["price"])
        # Timestamp of the trade.
        self.timestamp = int(_trade["time"])

    def __call__(self):
        return self


class OrderUpdate(OrderUpdate):
    def __init__(self, event: OrderUpdateWrapper) -> None:
        super().__init__()

        class OriginalOrder:
            def __init__(self, _event: OrderUpdateWrapper):
                self.id = _event.order_id

        # Original order previous to this update.
        self.original_order = OriginalOrder(event)
        # Trades that belong to the order, if any exist so far.
        self.resulting_trades = []
        for trade in ms.Strategy.trades:
            if trade.order_id == event.order_id:
                self.resulting_trades.append(trade)
        # Update status defining what happened to the order since the last update.
        if event.order_status == 'FILLED':
            self.status = OrderUpdate.FILLED
        elif event.order_status == 'PARTIALLY_FILLED':
            self.status = OrderUpdate.PARTIALLY_FILLED
        elif event.order_status == 'CANCELED':
            self.status = OrderUpdate.CANCELED
        else:
            self.status = OrderUpdate.OTHER_CHANGE
        # Time of the change.
        self.timestamp = int(event.transaction_time)
        # Newly updated order
        self.updated_order = None

    def __call__(self):
        return self


class Order:
    def __init__(self, order: {}) -> None:
        # Overall amount of the order.
        self.amount = float(order['origQty'])
        # True if the order is a buy order.
        self.buy = bool(order['side'] == 'BUY')
        # id of the order.
        self.id = int(order['orderId'])
        # Type of the order.
        self.order_type = order['type']
        # Price of the order.
        self.price = float(order['price'])
        # Amount that has been filled already.
        self.received_amount = float(order['executedQty'])
        # Amount that has not been filled yet.
        self.remaining_amount = float(ms.f2d(self.amount) - ms.f2d(self.received_amount))
        # Timestamp of the order.
        self.timestamp = int(order.get('transactTime', order.get('time', time.time())))

    def __call__(self):
        return self


class Candle:
    def __init__(self, _candle: []) -> None:
        # Start time of the candle.
        self.min_time = int(_candle[0])
        # Price of the first trade in the candle.
        self.open = float(_candle[1])
        # Highest traded price in the candle.
        self.high = float(_candle[2])
        # Lowest traded price in the candle.
        self.low = float(_candle[3])
        # Price of the last trade in the candle.
        self.close = float(_candle[4])
        # Volume traded within the candle.
        self.volume = float(_candle[5])
        # Time of the latest trade in the candle or closing time of the candle.
        self.max_time = int(_candle[6])
        # Number of trades included in the candle.
        self.trade_number = int(_candle[8])
        # Value weighted average price of the candle.
        self.vwap = (float(_candle[7]) / self.volume) if self.volume else self.close

    def __call__(self):
        return self


class TradingCapabilityManager:
    def __init__(self, _exchange_info_symbol):
        self.base_asset_precision = int(_exchange_info_symbol.get('baseAssetPrecision'))
        self.quote_asset_precision = int(_exchange_info_symbol.get('quoteAssetPrecision'))
        self.min_qty = float(_exchange_info_symbol['filters']['lotSize']['minQty'])
        self.max_qty = float(_exchange_info_symbol['filters']['lotSize']['maxQty'])
        self.step_size = float(_exchange_info_symbol['filters']['lotSize']['stepSize'])
        self.min_notional = float(_exchange_info_symbol['filters']['minNotional']['minNotional'])
        self.tick_size = float(_exchange_info_symbol['filters']['priceFilter']['tickSize'])

    def __call__(self):
        return self

    def round_amount(self, unrounded_amount: float, rounding_type: RoundingType) -> float:
        k = next((i for i, x in enumerate(f"{self.step_size:.10f}") if x not in ('.', '0')), 0)
        k = max(k - 1, 0)
        n = 10 ** k
        if rounding_type == RoundingType.CEIL:
            rounded_amount = math.ceil(unrounded_amount * n) / n if k else math.ceil(unrounded_amount)
        elif rounding_type == RoundingType.FLOOR:
            rounded_amount = math.floor(unrounded_amount * n) / n if k else math.floor(unrounded_amount)
        elif rounding_type == RoundingType.ROUND:
            rounded_amount = round(unrounded_amount, self.base_asset_precision)
        else:
            rounded_amount = unrounded_amount
            ms.Strategy.strategy.message_log("round_amount: Unknown RoundingType", log_level=LogLevel.ERROR)
        return rounded_amount

    def round_price(self, unrounded_price: float, rounding_type: RoundingType) -> float:
        k = f"{self.tick_size:.8f}".replace('5', '1').find('1') - 1
        k = k if k > 0 else 0
        n = 10 ** k
        if rounding_type == RoundingType.CEIL:
            rounded_price = math.ceil(unrounded_price * n) / n if k else math.ceil(unrounded_price)
        elif rounding_type == RoundingType.FLOOR:
            rounded_price = math.floor(unrounded_price * n) / n if k else math.floor(unrounded_price)
        elif rounding_type == RoundingType.ROUND:
            rounded_price = round(unrounded_price, k)
        else:
            rounded_price = unrounded_price
            ms.Strategy.strategy.message_log("round_price: Unknown RoundingType", log_level=LogLevel.ERROR)
        return rounded_price

    def get_min_sell_amount(self, price: float) -> float:
        # print(f"get_min_sell_amount: price:{price}, min_qty:{self.min_qty}, min_notional:{self.min_notional}")
        return max(self.min_qty, self.round_amount(self.min_notional / price, RoundingType.CEIL))

    def get_max_sell_amount(self, _unused_price: float) -> float:
        """
        Returns the maximally possible sell amount that can be placed at a given price.
        """
        return self.max_qty

    def get_min_buy_amount(self, price: float) -> float:
        # print(f"get_min_buy_amount: price:{price}, min_notional:{self.min_notional}")
        return self.round_amount(self.min_notional / price, RoundingType.CEIL)

    def get_minimal_price_change(self, _unused_price: float) -> float:
        return self.tick_size

    def get_minimal_amount_change(self, _unused_reference_amount: float = None) -> float:
        """
        Get the minimal amount change that is possible to use on the exchange.
        """
        return self.step_size


class Ticker:
    def __init__(self, _ticker):
        # Price of the currency pair one day ago.
        self.last_day_price = float(_ticker.get('openPrice'))
        # Last traded price of the currency pair.
        self.last_price = float(_ticker.get('lastPrice'))
        # Timestamp of the ticker data.
        self.timestamp = int(_ticker.get('closeTime'))
        # print(f"self.last_price: {self.last_price}")

    def __call__(self):
        return self


class FundsEntry:
    def __init__(self, _funds):
        # The available amount for a currency.
        self.available = float(_funds.get('free'))
        # The reserved amount for a currency.
        self.reserved = float(_funds.get('locked'))
        # Total amount of a currency in the account.
        self.total_for_currency = float(Decimal(_funds.get('free')) + Decimal(_funds.get('locked')))
        # print(f"self.total_for_currency: {self.total_for_currency}")

    def __call__(self):
        return self


class OrderBook:
    """
    order_book.bids[0].price
    order_book.asks[0].amount
    """
    def __init__(self, _order_book) -> None:
        class _OrderBookRow:
            def __init__(self, _order) -> None:
                self.price = float(_order[0])
                self.amount = float(_order[1])
        self.asks = []
        # List of asks ordered by price in ascending order.
        self.bids = []
        # List of bids ordered by price in descending order.
        for _, v in enumerate(_order_book['asks']):
            self.asks.append(_OrderBookRow(v))
        for _, v in enumerate(_order_book['bids']):
            self.bids.append(_OrderBookRow(v))

    def __call__(self):
        return self


def heartbeat():
    while ms.Strategy.strategy:
        last_state = ms.Strategy.strategy.save_strategy_state()
        # print(f"tik-tak ', {time.time()}")
        last_state['ms.order_id'] = json.dumps(ms.Strategy.order_id)
        last_state['ms_start_time_ms'] = json.dumps(ms.Strategy.start_time_ms)
        last_state['ms.orders'] = jsonpickle.encode(ms.Strategy.orders)
        # print(f"heartbeat.last_state: {last_state}")
        if os.path.exists(ms.FILE_LAST_STATE):
            os.rename(ms.FILE_LAST_STATE, f"{ms.FILE_LAST_STATE}.prev")
        with open(ms.FILE_LAST_STATE, 'w') as outfile:
            json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
        time.sleep(HEARTBEAT)


async def save_asset(_stub, _client_id, _base_asset, _quote_asset):
    """
    Update account asset list and value in t_asset
    """
    session = ms.Strategy.strategy
    connection_analytic = None
    while connection_analytic is None:
        connection_analytic = session.connection_analytic
        await asyncio.sleep(HEARTBEAT)
    delay = HEARTBEAT * 300  # 10 min
    max_use_update = 60 * 60 * 24  # 24h if the row has not been updated that the asset is not traded
    id_ftx_main = ms.EXCHANGE.index('FTX') if ms.Strategy.exchange == 'ftx' and ms.EXCHANGE.count('FTX') else None
    if ms.Strategy.exchange == 'ftx' and id_ftx_main is None:
        ms.Strategy.strategy.message_log("For FTX exchange main account name want be 'FTX'", log_level=LogLevel.WARNING)
    while True:
        try:
            res = await _stub.FetchAccountInformation(api_pb2.OpenClientConnectionId(client_id=_client_id))
        except asyncio.CancelledError:
            print("save_asset.Cancelled")
        except Exception as _ex:
            ms.Strategy.strategy.message_log(f"Exception save_asset: {_ex}", log_level=LogLevel.WARNING)
        else:
            balances = json_format.MessageToDict(res).get('balances', [])
            # Refresh actual balance
            try:
                balance_f = next(item for item in balances if item["asset"] == _base_asset)
            except StopIteration:
                balance_f = {'asset': _base_asset, 'free': '0.0', 'locked': '0.0'}
            try:
                balance_s = next(item for item in balances if item["asset"] == _quote_asset)
            except StopIteration:
                balance_s = {'asset': _base_asset, 'free': '0.0', 'locked': '0.0'}
            funds = {_base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                     _quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
            ms.Strategy.funds = funds
            # Get asset balances from Funding Wallet
            cursor = connection_analytic.cursor()
            try:
                cursor.execute('SELECT 1 FROM t_asset WHERE id_exchange=:id_exchange AND use=:use',
                               {'id_exchange': id_ftx_main or ms.ID_EXCHANGE, 'use': 1})
                ftx_main_active = cursor.fetchone()
                cursor.close()
            except sqlite3.Error as err:
                cursor.close()
                ftx_main_active = (2,)
                print(f"SELECT from t_asset: {err}")
            funding_wallet = []
            assets_fw = {}
            if ((id_ftx_main is None or (ftx_main_active is None and id_ftx_main != ms.ID_EXCHANGE))
                    and ms.Strategy.exchange != 'bitfinex'):
                try:
                    res = await _stub.FetchFundingWallet(
                                    api_pb2.FetchFundingWalletRequest(client_id=_client_id)
                    )
                except asyncio.CancelledError:
                    print("save_asset.Cancelled")
                except Exception as _ex:
                    ms.Strategy.strategy.message_log(f"FetchFundingWallet: {_ex}", log_level=LogLevel.WARNING)
                else:
                    funding_wallet = json_format.MessageToDict(res).get('balances', [])
                for fw in funding_wallet:
                    assets_fw[fw['asset']] = Decimal(fw['free']) + Decimal(fw['locked']) + Decimal(fw['freeze'])
            # Create list of cumulative asset without current pair, from SPOT wallet
            # and all assets from Funding wallet on Binance or main account on FTX
            assets = {}
            for balance in balances:
                if id_ftx_main is None and ms.Strategy.exchange != 'bitfinex':
                    total = assets_fw.pop(balance['asset'], Decimal('0.0'))
                else:
                    total = Decimal('0.0')
                if balance['asset'] not in (_base_asset, _quote_asset):
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
                if id_ftx_main is None or ms.ID_EXCHANGE == id_ftx_main or ftx_main_active is None:
                    cursor.execute('DELETE\
                                    FROM t_asset\
                                    WHERE id_exchange=:id_exchange\
                                    and use=:use',
                                   {'id_exchange': id_ftx_main or ms.ID_EXCHANGE, 'use': 0})
                for row in rows:
                    if row[1] in (_base_asset, _quote_asset):
                        if ftx_main_active == (1,):
                            assets.pop(row[1], None)
                            cursor.execute('UPDATE t_asset SET value=:value, timestamp=:timestamp, use=:use\
                                            WHERE id_exchange=:id_exchange\
                                            and currency=:currency',
                                           {'value': 0.0, 'timestamp': int(time.time()), 'use': 1,
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
                        use = 1 if key in (_base_asset, _quote_asset) else 0
                        cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                       (ms.ID_EXCHANGE, key, value, use, int(time.time())))
                if assets_fw:
                    for key, value in assets_fw.items():
                        cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                       (id_ftx_main or ms.ID_EXCHANGE, key, float(value), 0, int(time.time())))
                cursor.execute('COMMIT')
                cursor.close()
            except sqlite3.Error as err:
                cursor.execute('ROLLBACK')
                cursor.close()
                print(f"Refresh t_asset: {err}")
        await asyncio.sleep(delay)


async def ask_exit(_loop):
    _stub = ms.Strategy.stub
    _client_id = ms.Strategy.client_id
    _symbol = ms.Strategy.symbol
    if ms.Strategy.strategy:
        ms.Strategy.strategy.message_log("Got signal for exit", color=ms.Style.MAGENTA)
        await _stub.StopStream(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol))
        tasks = [t for t in asyncio.all_tasks(_loop) if t is not asyncio.current_task(_loop)]
        [task.cancel() for task in tasks]
        print(f"Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks, loop=_loop, return_exceptions=True)
        try:
            ms.Strategy.strategy.stop()
        except Exception as _err:
            print(f"ask_exit.strategy.stop: {_err}")
        ms.Strategy.strategy = None
        if os.path.exists(ms.FILE_LAST_STATE):
            answer = input('Save current state? y/n:\n')
            if answer.lower() != 'y':
                if os.path.exists(ms.FILE_LAST_STATE + '.bak'):
                    os.remove(ms.FILE_LAST_STATE + '.bak')
                os.rename(ms.FILE_LAST_STATE, ms.FILE_LAST_STATE + '.bak')
                print('Current state cleared')
            else:
                print('OK')


async def buffered_candle(_stub, _client_id, _symbol):
    StrategyBase.Klines.klines_lim = KLINES_LIM
    klines = {}
    for i in KLINES_INIT:
        res = await _stub.FetchKlines(api_pb2.FetchKlinesRequest(
            client_id=_client_id,
            symbol=_symbol,
            interval=i.value,
            limit=KLINES_LIM))
        kline = json_format.MessageToDict(res)
        # print(f"buffered_candle.kline: {kline}")
        kline_i = StrategyBase.Klines(i.value)
        for candle in kline.get('klines', []):
            kline_i.refresh(json.loads(candle))
            # print(f"buffered_candle.candle: {candle}")
        klines[i.value] = kline_i
    loop.create_task(on_klines_update(_stub, _client_id, _symbol, klines))


async def on_klines_update(_stub, _client_id, _symbol, _klines):
    _interval = json.dumps(list(_klines.keys()))
    async for candle in _stub.OnKlinesUpdate(api_pb2.FetchKlinesRequest(
            client_id=_client_id,
            symbol=_symbol,
            interval=_interval)):
        # print(f"on_klines_update: {candle.symbol}, {candle.interval}")
        _klines.get(candle.interval).refresh(json.loads(candle.candle))


async def buffered_funds(_stub, _client_id, _symbol, _base_asset, _quote_asset, print_info: bool = True):
    try:
        res = await _stub.FetchAccountInformation(api_pb2.OpenClientConnectionId(client_id=_client_id))
    except asyncio.CancelledError:
        logger.info("buffered_funds.Cancelled")
    except Exception as _ex:
        logger.warning(f"Exception buffered_funds: {_ex}")
    else:
        balances = json_format.MessageToDict(res).get('balances', [])
        # print(f"buffered_funds.balances: {balances}")
        try:
            balance_f = next(item for item in balances if item["asset"] == _base_asset)
        except StopIteration:
            balance_f = {'asset': _base_asset, 'free': '0.0', 'locked': '0.0'}
        try:
            balance_s = next(item for item in balances if item["asset"] == _quote_asset)
        except StopIteration:
            balance_s = {'asset': _quote_asset, 'free': '0.0', 'locked': '0.0'}
        funds = {_base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                 _quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
        cls = ms.Strategy
        cls.funds = funds
        if print_info:
            print('================================================================')
            print(f"Base asset balance: {balance_f}")
            print(f"Quote asset balance: {balance_s}")
            print('================================================================')
        else:
            # print(f"buffered_funds.funds: {cls.funds}")
            funds = {cls.base_asset: FundsEntry(cls.funds[cls.base_asset]),
                     cls.quote_asset: FundsEntry(cls.funds[cls.quote_asset])}
            cls.strategy.on_new_funds(funds)


async def buffered_orders(_stub, _client_id, _symbol):
    all_orders = []
    exch_orders_id = []
    save_orders_id = []
    restore = False
    run = True
    while run:
        try:
            _orders = await _stub.FetchOpenOrders(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol))
            StrategyBase.rate_limiter = max(StrategyBase.rate_limiter, _orders.rate_limiter)
            orders = json_format.MessageToDict(_orders).get('items', [])
            # print(f"buffered_orders.orders: {orders}")
            part_id = []
            for order in orders:
                _id = int(order['orderId'])
                all_orders.append(Order(order))
                exch_orders_id.append(_id)
                if (order.get('status', None) == 'PARTIALLY_FILLED'
                        and order_trades_sum(_id) < Decimal(order['executedQty'])):
                    part_id.append(_id)
            for i in ms.Strategy.all_orders:
                save_orders_id.append(i.id)
            # Missed fill event list
            diff_id = list(set(save_orders_id).difference(exch_orders_id))
            # print(f"buffered_orders.diff_id: {diff_id}")
            # Erroneously not deleted order
            diff_excess_id = list(set(exch_orders_id).
                                  difference(save_orders_id).
                                  intersection(ms.Strategy.canceled_order_id))
            # print(f"buffered_orders.diff_excess_id: {diff_excess_id}")
            exch_orders_id.clear()
            save_orders_id.clear()
            if not ms.Strategy.last_state and (diff_id or part_id):
                ms.Strategy.strategy.message_log(f"Perhaps was missed event for order(s): {diff_id + part_id},"
                                                 f" checking it", log_level=LogLevel.WARNING, tlg=False)
                for _id in list(set(diff_id + part_id)):
                    await fetch_order(_id, _filled_update_call=True)
                part_id.clear()
            if not ms.Strategy.last_state and diff_excess_id:
                ms.Strategy.strategy.message_log(f"Find excess order(s): {diff_excess_id}, checking it",
                                                 log_level=LogLevel.WARNING, tlg=False)
                for _id in diff_excess_id:
                    check_status = await fetch_order(_id, _filled_update_call=False)
                    if check_status.get('status') not in ('FILLED', 'CANCELED'):
                        ms.Strategy.strategy.message_log(f"buffered_orders.create_task: cancel_order: {_id}",
                                                         log_level=LogLevel.INFO)
                        loop.create_task(cancel_order_timeout(_id))
                        loop.create_task(cancel_order_call(_id))
            ms.Strategy.all_orders = all_orders.copy()
            all_orders.clear()
            if restore or ms.Strategy.last_state:
                if restore:
                    ms.Strategy.strategy.message_log("Trying restore saved state after lost connection to host",
                                                     color=ms.Style.GREEN)
                else:
                    ms.Strategy.strategy.message_log("Trying restore saved state after restart", color=ms.Style.GREEN)
                try:
                    last_state = {}
                    if ms.Strategy.last_state:
                        last_state.update(ms.Strategy.last_state)
                        ms.Strategy.last_state = None
                        # Restore StrategyBase class var
                        ms.Strategy.order_id = json.loads(last_state.pop('ms.order_id', 0))
                        ms.Strategy.start_time_ms = json.loads(last_state.pop('ms_start_time_ms',
                                                                              str(int(time.time() * 1000)))
                                                               )
                        #
                        ms.Strategy.orders = jsonpickle.decode(last_state.pop('ms.orders', '[]'))
                        # print(f"buffered_orders.ms.orders: {ms.Strategy.orders}")
                    else:
                        last_state.pop('ms.order_id', None)
                        # last_state.pop('ms.trades', None)
                        last_state.pop('ms.orders', None)
                    # Get trades for strategy
                    _trades = await _stub.FetchAccountTradeList(api_pb2.AccountTradeListRequest(
                        client_id=_client_id,
                        symbol=_symbol,
                        limit=ALL_TRADES_LIST_LIMIT,
                        start_time=ms.Strategy.start_time_ms)
                    )
                    trades = json_format.MessageToDict(_trades).get('items', [])
                    # print(f"main.trades: {trades}")
                    for trade in trades:
                        ms.Strategy.all_trades.append(PrivateTrade(trade))
                    # Update StrategyBase class var
                    exch_orders_id = []
                    ms_orders_id = []
                    for i in ms.Strategy.all_orders:
                        exch_orders_id.append(i.id)
                    for i in ms.Strategy.orders:
                        ms_orders_id.append(i.id)
                    # print(f"buffered_orders.exch_orders_id: {exch_orders_id}")
                    # print(f"buffered_orders.ms_orders_id: {ms_orders_id}")
                    diff_id = list(set(ms_orders_id).difference(exch_orders_id))
                    if diff_id:
                        ms.Strategy.strategy.message_log(f"Executed order(s) is: {diff_id}", log_level=LogLevel.INFO)
                        for _id in diff_id:
                            remove_from_trades_lists(_id)
                            for i, o in enumerate(ms.Strategy.orders):
                                if o.id == _id and trade_not_exist(_id, 1):
                                    # Add completed trades to list
                                    trade = {"qty": o.amount,
                                             "isBuyer": o.buy,
                                             "id": 1,
                                             "orderId": o.id,
                                             "price": o.price,
                                             "time": o.timestamp}
                                    # print(f"buffered_orders.trade: {trade}")
                                    if len(ms.Strategy.trades) > TRADES_LIST_LIMIT:
                                        del ms.Strategy.trades[0]
                                    ms.Strategy.trades.append(PrivateTrade(trade))
                                    if len(ms.Strategy.all_trades) > ALL_TRADES_LIST_LIMIT:
                                        del ms.Strategy.all_trades[0]
                                    ms.Strategy.all_trades.append(PrivateTrade(trade))
                    # Delete from orders list
                    remove_from_orders_lists(diff_id)
                    # print(f"buffered_orders.ms.Strategy.orders: {ms.Strategy.orders}")
                    if not restore:
                        ms.Strategy.strategy.restore_strategy_state(last_state)
                except Exception as exc:
                    ms.Strategy.last_state = None
                    ms.Strategy.strategy.message_log(f"Exception restore_strategy_state: {exc}",
                                                     log_level=LogLevel.WARNING)
                restore = False
        except asyncio.CancelledError:
            # print("buffered_orders.Cancelled")
            run = False
        except grpc.RpcError as ex:
            status_code = ex.code()
            ms.Strategy.strategy.message_log(f"Exception buffered_orders: {status_code.name}, {ex.details()}",
                                             log_level=LogLevel.WARNING)
            if status_code == grpc.StatusCode.RESOURCE_EXHAUSTED:
                # Decrease requests frequency if not FTX exchange
                if not ms.FEE_FTX:
                    StrategyBase.rate_limiter += HEARTBEAT
                    ms.Strategy.strategy.message_log(f"RATE_LIMITER set to {StrategyBase.rate_limiter}s",
                                                     log_level=LogLevel.WARNING)
                await asyncio.sleep(ORDER_TIMEOUT)
                await _stub.ResetRateLimit(api_pb2.OpenClientConnectionId(
                    client_id=_client_id,
                    rate_limiter=StrategyBase.rate_limiter))
            else:
                restore = True
        except Exception as _ex:
            ms.Strategy.strategy.message_log(f"Exception buffered_orders: {_ex}\n"
                                             f"{ms.traceback.print_exc()}",  # lgtm [py/procedure-return-value-used]
                                             log_level=LogLevel.ERROR)
            restore = True
        await asyncio.sleep(StrategyBase.rate_limiter)


async def on_funds_update(_stub, _client_id, _symbol, _base_asset, _quote_asset):
    async for _funds in _stub.OnFundsUpdate(api_pb2.OnFundsUpdateRequest(
            client_id=_client_id,
            symbol=_symbol,
            base_asset=_base_asset,
            quote_asset=_quote_asset)
    ):
        funds = json.loads(json.loads(json_format.MessageToJson(_funds))['funds'])
        if funds.get(_base_asset) and funds.get(_quote_asset):
            ms.Strategy.funds = funds
            # print(f"on_funds_update.funds: {funds}")
            funds = {_base_asset: FundsEntry(funds[_base_asset]),
                     _quote_asset: FundsEntry(funds[_quote_asset])}
            ms.Strategy.strategy.on_new_funds(funds)
            ms.Strategy.get_buffered_funds_last_time = time.time()


async def on_order_update(_stub, _client_id, _symbol):
    async for event in _stub.OnOrderUpdate(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol)):
        # Only for registered orders on own pair
        '''
        print(f"on_order_update: {event.symbol}\n"
              f"order_id: {event.order_id}\n"
              f"trade_id: {event.trade_id}\n"
              f"order_status: {event.order_status}\n")
        '''
        if (_symbol == event.symbol
                and ms.Strategy.order_exist(event.order_id)
                and event.order_status in ('FILLED', 'PARTIALLY_FILLED')):
            '''
            print(f"on_order_update: {event.symbol}\n"
                  f"order_id: {event.order_id}\n"
                  f"trade_id: {event.trade_id}\n"
                  f"order_status: {event.order_status}\n"
                  f"cumulative_filled_quantity: {event.cumulative_filled_quantity}\n"
                  f"last_executed_quantity: {event.last_executed_quantity}\n"
                  f"quote_order_quantity: {event.quote_order_quantity}\n"
                  f"quote_asset_transacted: {event.quote_asset_transacted}\n"
                  f"client_order_id: {event.client_order_id}")
            '''
            if event.order_status == 'FILLED':
                # Remove from all_orders and orders lists
                remove_from_orders_lists([event.order_id])
            if trade_not_exist(event.order_id, event.trade_id):
                trade = {"qty": event.last_executed_quantity,
                         "isBuyer": bool(event.side == 'BUY'),
                         "id": event.trade_id,
                         "orderId": event.order_id,
                         "price": event.last_executed_price,
                         "time": event.transaction_time}
                #  Append to all_trades and trades list
                if len(ms.Strategy.trades) > TRADES_LIST_LIMIT:
                    del ms.Strategy.trades[0]
                ms.Strategy.trades.append(PrivateTrade(trade))
                if len(ms.Strategy.all_trades) > ALL_TRADES_LIST_LIMIT:
                    del ms.Strategy.all_trades[0]
                    ms.Strategy.all_trades.append(PrivateTrade(trade))
                cumulative_quantity = Decimal(event.cumulative_filled_quantity)
                saved_filled_quantity = order_trades_sum(event.order_id)
                if event.order_status == 'FILLED' and saved_filled_quantity != cumulative_quantity:
                    if not ms.FEE_FTX:
                        ms.Strategy.strategy.message_log(f"Order: {event.order_id} was missed partially filling event",
                                                         log_level=LogLevel.INFO)
                    # Remove trades associated with order from list
                    remove_from_trades_lists(event.order_id)
                    # Update current trade
                    price = str(Decimal(event.quote_asset_transacted) / Decimal(event.cumulative_filled_quantity))
                    trade.update({"qty": event.cumulative_filled_quantity, "price": price})
                    # ms.Strategy.strategy.message_log(f"on_order_update.trade: {trade}",
                    #                                  log_level=LogLevel.DEBUG, color=ms.Style.YELLOW)
                    # Append to list
                    ms.Strategy.trades.append(PrivateTrade(trade))
                    ms.Strategy.all_trades.append(PrivateTrade(trade))
                ms.Strategy.strategy.on_order_update(OrderUpdate(event))


async def create_limit_order(_id: int, buy: bool, amount: str, price: str) -> None:
    try:
        res = await ms.Strategy.stub.CreateLimitOrder(api_pb2.CreateLimitOrderRequest(
            client_id=ms.Strategy.client_id,
            symbol=ms.Strategy.symbol,
            buy_side=buy,
            quantity=amount,
            price=price,
            new_client_order_id=_id
        ))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error
    except grpc.RpcError as ex:
        status_code = ex.code()
        ms.Strategy.strategy.message_log(f"Exception creating order {_id}: {status_code.name}, {ex.details()}")
        if status_code == grpc.StatusCode.FAILED_PRECONDITION:
            ms.Strategy.strategy.message_log('Error code: FAILED_PRECONDITION')
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Exception creating order {_id}: {_ex}")
    else:
        # ms.Strategy.strategy.message_log(f"Create_limit_order.result: {result}",
        #                                  log_level=LogLevel.DEBUG, color=ms.Style.UNDERLINE)
        if result:
            ms.Strategy.wait_order_id.append(_id)
            order = Order(result)
            ms.Strategy.strategy.message_log(
                f"Order placed {order.id}({result.get('clientOrderId') or _id}) for {result.get('side')}"
                f" {order.amount} by {order.price} Remaining amount {order.remaining_amount}",
                color=ms.Style.GREEN)
            orig_qty = Decimal(result['origQty'])
            executed_qty = Decimal(result['executedQty'])
            cummulative_quote_qty = Decimal(result['cummulativeQuoteQty'])
            if executed_qty > 0:
                price = float(cummulative_quote_qty / executed_qty)
                trade = {"qty": float(executed_qty),
                         "isBuyer": order.buy,
                         "id": int(time.time() * 1000),
                         "orderId": order.id,
                         "price": price,
                         "time": order.timestamp}
                # ms.Strategy.strategy.message_log(f"place_limit_order_callback.trade: {trade}", color=ms.Style.YELLOW)
                if len(ms.Strategy.trades) > TRADES_LIST_LIMIT:
                    del ms.Strategy.trades[0]
                ms.Strategy.trades.append(PrivateTrade(trade))
                if len(ms.Strategy.all_trades) > ALL_TRADES_LIST_LIMIT:
                    del ms.Strategy.all_trades[0]
                ms.Strategy.all_trades.append(PrivateTrade(trade))
            if executed_qty < orig_qty:
                ms.Strategy.orders.append(order)
                ms.Strategy.all_orders.append(order)
            ms.Strategy.strategy.on_place_order_success(_id, order)


async def place_limit_order_timeout(_id):
    await asyncio.sleep(ORDER_TIMEOUT)
    if _id in ms.Strategy.wait_order_id:
        ms.Strategy.wait_order_id.remove(_id)
    else:
        ms.Strategy.strategy.on_place_order_error_string(_id, 'Place order timeout')


async def cancel_order_call(_id: int):
    try:
        res = await ms.Strategy.stub.CancelOrder(api_pb2.CancelOrderRequest(
            client_id=ms.Strategy.client_id,
            symbol=ms.Strategy.symbol,
            order_id=_id))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except grpc.RpcError as ex:
        status_code = ex.code()
        ms.Strategy.strategy.message_log(f"Exception on cancel order for {_id}: {status_code.name}, {ex.details()}")
        await asyncio.sleep(HEARTBEAT)
        if status_code == grpc.StatusCode.UNKNOWN:
            check_status = await fetch_order(_id, _filled_update_call=True)
            if check_status.get('status') == 'CANCELED':
                # For stop timeout firing
                ms.Strategy.canceled_order_id.append(_id)
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Exception on cancel order call for {_id}:\n{_ex}")
    else:
        # print(f"cancel_order_call.result: {result}")
        # Remove from all_orders and orders lists
        if result:
            remove_from_orders_lists([_id])
            ms.Strategy.strategy.message_log(f"Cancel order {_id} success", color=ms.Style.GREEN)
            ms.Strategy.strategy.on_cancel_order_success(_id, Order(result))
            ms.Strategy.canceled_order_id.append(_id)


async def cancel_order_timeout(_id):
    await asyncio.sleep(ORDER_TIMEOUT)
    if _id in ms.Strategy.canceled_order_id:
        ms.Strategy.canceled_order_id.remove(_id)
    else:
        ms.Strategy.strategy.on_cancel_order_error_string(_id, 'Cancel order timeout')


async def fetch_order(_id: int, _filled_update_call: bool = False):
    try:
        res = await ms.Strategy.stub.FetchOrder(api_pb2.FetchOrderRequest(
            client_id=ms.Strategy.client_id,
            symbol=ms.Strategy.symbol,
            order_id=_id,
            filled_update_call=_filled_update_call))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Exception in fetch_order: {_ex}", log_level=LogLevel.ERROR)
        return {}
    else:
        ms.Strategy.strategy.message_log(f"For order {result.get('orderId')} fetched status is {result.get('status')}",
                                         log_level=LogLevel.INFO)
        if _filled_update_call and result and result.get('status') == 'CANCELED':
            remove_from_orders_lists([_id])
            ms.Strategy.strategy.message_log(f"Cancel order {_id} OK", color=ms.Style.GREEN)
            ms.Strategy.strategy.on_cancel_order_success(_id, Order(result))
            # await asyncio.sleep(ORDER_TIMEOUT / 3)
            ms.Strategy.canceled_order_id.append(_id)
        return result


def remove_from_orders_lists(_order_id_list: []) -> None:
    # print(f"remove_from_orders_lists._order_id: {_order_id}")
    ms.Strategy.orders[:] = [i for i in ms.Strategy.orders if i.id not in _order_id_list]
    ms.Strategy.all_orders[:] = [i for i in ms.Strategy.all_orders if i.id not in _order_id_list]


def remove_from_trades_lists(_order_id) -> None:
    # print(f"remove_from_trades_lists._order_id: {_order_id}")
    ms.Strategy.trades[:] = [i for i in ms.Strategy.trades if i.order_id != _order_id]
    ms.Strategy.all_trades[:] = [i for i in ms.Strategy.all_trades if i.order_id != _order_id]


async def on_ticker_update(_stub, _client_id, _symbol):
    async for ticker in _stub.OnTickerUpdate(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol)):
        ticker_24h = {'openPrice': ticker.open_price,
                      'lastPrice': ticker.close_price,
                      'closeTime': ticker.event_time}
        ms.Strategy.ticker = ticker_24h
        ms.Strategy.strategy.on_new_ticker(Ticker(ms.Strategy.ticker))
        # print(f"on_ticker_update: {ticker.symbol} {ms.Strategy.ticker['closeTime']}")


async def on_order_book_update(_stub, _client_id, _symbol):
    async for _order_book in _stub.OnOrderBookUpdate(api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol)):
        order_book = json_format.MessageToDict(_order_book)
        order_book_bids = order_book.pop('bids', [])
        order_book_asks = order_book.pop('asks', [])
        _bids = []
        for bid in order_book_bids:
            _bids.append(json.loads(bid))
        _asks = []
        for ask in order_book_asks:
            _asks.append(json.loads(ask))
        order_book.update({'bids': _bids})
        order_book.update({'asks': _asks})
        # print(f"on_order_book_update.order_book: {order_book}")
        ms.Strategy.order_book = order_book
        ms.Strategy.strategy.on_new_order_book(OrderBook(ms.Strategy.order_book))


def load_last_state() -> {}:
    def load_file(name) -> {}:
        _res = {}
        if os.path.exists(name):
            try:
                with open(name) as state_file:
                    _last_state = json.load(state_file)
            except json.JSONDecodeError as er:
                print(f"Exception on decode last state file: {er}")
            else:
                # TODO Correct on next version
                # if _last_state.get('ms.start_time_ms', None):
                if _last_state.get('ms_start_time_ms', _last_state.get('ms.start_time_ms', None)):
                    _res = _last_state
        return _res

    res = {}
    if os.path.exists(ms.FILE_LAST_STATE):
        res = load_file(ms.FILE_LAST_STATE)
        if not res:
            print("Can't load last state, try load previous saved state")
            res = load_file(f"{ms.FILE_LAST_STATE}.prev")
        if res:
            with open(ms.FILE_LAST_STATE + '.bak', 'w') as outfile:
                json.dump(res, outfile, sort_keys=True, indent=4, ensure_ascii=False)
    return res


async def main(_symbol):
    ms.Strategy.symbol = _symbol
    StrategyBase.symbol = _symbol
    # ms.Strategy.loop = loop
    account_name = ms.EXCHANGE[ms.ID_EXCHANGE]
    print(f"main.account_name: {account_name}")  # lgtm [py/clear-text-logging-sensitive-data]
    channel = grpc.aio.insecure_channel(target='localhost:50051', options=CHANNEL_OPTIONS)
    stub = api_pb2_grpc.MartinStub(channel)
    client_id = None
    exchange = None
    try:
        client_id_msg = await stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
            account_name=account_name,
            rate_limiter=StrategyBase.rate_limiter))
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except grpc.RpcError as ex:
        # noinspection PyUnresolvedReferences
        status_code = ex.code()
        # noinspection PyUnresolvedReferences
        print(f"Exception on register client: {status_code.name}, {ex.details()}")
        # noinspection PyProtectedMember, PyUnresolvedReferences
        os._exit(1)
    else:
        client_id = client_id_msg.client_id
        exchange = client_id_msg.exchange
        print(f"main.exchange: {exchange}")
        print(f"main.client_id: {client_id}")
        print(f"main.srv_version: {client_id_msg.srv_version}")
    ms.Strategy.exchange = exchange
    ms.Strategy.stub = stub
    ms.Strategy.client_id = client_id
    # Check and Cancel ALL ACTIVE ORDER
    _active_orders = await stub.FetchOpenOrders(api_pb2.MarketRequest(client_id=client_id,
                                                                      symbol=_symbol))
    # print(f"main._active_orders: {_active_orders}")
    active_orders = json_format.MessageToDict(_active_orders).get('items', [])
    # print(f"main.active_orders: {active_orders}")
    # Try load last strategy state from saved files
    last_state = load_last_state()
    restore_state = bool(last_state)
    print(f"main.restore_state: {restore_state}")
    if CANCEL_ALL_ORDERS and active_orders and not ms.LOAD_LAST_STATE:
        answer = input('Are you want cancel all active order for this pair? Y:\n')
        if answer.lower() == 'y':
            restore_state = False
            await stub.CancelAllOrders(
                api_pb2.MarketRequest(
                    client_id=client_id,
                    symbol=_symbol
                ))
            cancel_orders = json_format.MessageToDict(_active_orders).get('items', [])
            print('Before start was canceled orders:')
            for i in cancel_orders:
                print(f"Order:{i['orderId']}, side:{i['side']}, amount:{i['origQty']}, price:{i['price']}")
            print('================================================================')
    # Init section
    _exchange_info_symbol = await stub.FetchExchangeInfoSymbol(
        api_pb2.MarketRequest(client_id=client_id, symbol=_symbol)
    )
    exchange_info_symbol = json_format.MessageToDict(_exchange_info_symbol)
    # print("\n".join(f"{k}\t{v}" for k, v in exchange_info_symbol.items()))
    filters = exchange_info_symbol.get('filters')
    for _filter in filters:
        print(f"{filters.get(_filter).pop('filterType')}: {filters.get(_filter)}")
    base_asset = exchange_info_symbol.get('baseAsset')
    quote_asset = exchange_info_symbol.get('quoteAsset')
    # init Strategy class var
    ms.Strategy.info_symbol = exchange_info_symbol
    ms.Strategy.tcm = TradingCapabilityManager(exchange_info_symbol)
    ms.Strategy.base_asset = base_asset
    ms.Strategy.quote_asset = quote_asset
    await buffered_funds(stub, client_id, _symbol, base_asset, quote_asset)
    # region Get and processing Order book
    _order_book = await stub.FetchOrderBook(api_pb2.MarketRequest(
        client_id=client_id,
        symbol=_symbol))
    order_book = json_format.MessageToDict(_order_book)
    order_book_bids = order_book.pop('bids', [])
    order_book_asks = order_book.pop('asks', [])
    _bids = []
    for bid in order_book_bids:
        _bids.append(json.loads(bid))
    _asks = []
    for ask in order_book_asks:
        _asks.append(json.loads(ask))
    order_book.update({'bids': _bids})
    order_book.update({'asks': _asks})
    if not order_book['bids'] or not order_book['asks']:
        _price = await stub.FetchSymbolPriceTicker(api_pb2.MarketRequest(
            client_id=client_id,
            symbol=_symbol))
        price = json_format.MessageToDict(_price)
        print(f"Not bids or asks for pair {price.get('symbol')}, last known price is {price.get('price')}")
        amount = exchange_info_symbol['filters']['lotSize']['minQty']
        order_book['bids'] = order_book['bids'] or [[price['price'], amount]]
        order_book['asks'] = order_book['asks'] or [[price['price'], amount]]
    # print(f"main.order_book: {order_book}")
    ms.Strategy.order_book = order_book
    # endregion
    _ticker = await stub.FetchTickerPriceChangeStatistics(api_pb2.MarketRequest(
        client_id=client_id,
        symbol=_symbol))
    ms.Strategy.ticker = json_format.MessageToDict(_ticker)
    # print(f"main.ticker: {ms.Strategy.ticker}")
    # init Strategy class
    m_strategy = ms.Strategy()
    # print(f"main.m_strategy: {m_strategy}")
    ms.Strategy.strategy = m_strategy
    await buffered_candle(stub, client_id, _symbol)
    # Market stream
    loop.create_task(on_ticker_update(stub, client_id, _symbol))
    loop.create_task(on_order_book_update(stub, client_id, _symbol))
    # User Stream
    loop.create_task(on_funds_update(stub, client_id, _symbol, base_asset, quote_asset))
    loop.create_task(on_order_update(stub, client_id, _symbol))
    # Start section
    '''
    market_stream_count=5, user_stream_count=2
    These values directly depend on the number of market and user ws streams used in the strategy and declared above
    '''
    await stub.StartStream(api_pb2.StartStreamRequest(client_id=client_id,
                                                      symbol=_symbol,
                                                      market_stream_count=5,
                                                      user_stream_count=2))
    loop.create_task(save_asset(stub, client_id, base_asset, quote_asset))
    answer = str()
    restored = True
    if restore_state:
        if last_state.get("command", None) == '"stopped"':
            input('Saved state was "stopped". Press Enter for continue or Ctrl-Z for Cancel\n')
            last_state["command"] = 'null'
        if not ms.LOAD_LAST_STATE:
            answer = input('Restore saved state after restart? Y:\n')
        if ms.LOAD_LAST_STATE or answer.lower() == 'y':
            ms.Strategy.last_state = last_state
            try:
                m_strategy.init(check_funds=False)
            except Exception as ex:
                print(f"Strategy init error: {ex}")
                restored = False
    loop.create_task(buffered_orders(stub, client_id, _symbol))
    if not restore_state or (not ms.LOAD_LAST_STATE and answer.lower() != 'y'):
        m_strategy.init()
        input('Press Enter for Start or Ctrl-Z for Cancel\n')
        m_strategy.start()
    if restored:
        loop.run_in_executor(None, heartbeat)
