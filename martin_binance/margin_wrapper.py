#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
margin Python wrapper mPw
margin.de <-> Python strategy <-> mPw <-> BinanceAPIServer <-> Python3 binance API wrapper <-> Binance API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.0rc1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
import functools
import simplejson as json
import logging
import math
import os
import sys
import time
from signal import SIGINT
from decimal import Decimal

# noinspection PyPackageRequirements
import grpc
import jsonpickle
# noinspection PyPackageRequirements
from google.protobuf import json_format
from margin_strategy_sdk import *

# noinspection PyPackageRequirements
import binance  # lgtm [py/import-and-import-from]
import binance_api_pb2
import binance_api_pb2_grpc
import executor as ms
# noinspection PyPackageRequirements
from binance import events

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [('grpc.lb_policy_name', 'pick_first'),
                   ('grpc.enable_retries', 0),
                   ('grpc.keepalive_timeout_ms', 10000)]

loop = asyncio.get_event_loop()
KLINES_INIT = [binance.Interval.ONE_MINUTE, binance.Interval.FIFTY_MINUTES, binance.Interval.ONE_HOUR]
KLINES_LIM = 100  # Number of candles must be <= 1000
CANCEL_ALL_ORDERS = True  # Ask about cancel all active orders before start strategy and ms.LOAD_LAST_STATE = 0
ALL_TRADES_LIST_LIMIT = 200
TRADES_LIST_LIMIT = 100
HEARTBEAT = 2  # Sec
RATE_LIMITER = HEARTBEAT * 5
ORDER_TIMEOUT = HEARTBEAT * 15  # Sec
logger = logging.getLogger('logger')


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
    symbol = str()
    stub = binance_api_pb2_grpc.MartinStub
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
            new_time = candle.min_time
            last_time = self.kline[-1].min_time if self.kline else 0
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
        for i in cls.orders:
            if i.id == _id:
                return True
        return False

    @classmethod
    def all_order_exist(cls, _id) -> bool:
        for i in cls.all_orders:
            if i.id == _id:
                return True
        return False

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


def trade_not_exist(_order_id: int, _trade_id: int, _trades: [PrivateTrade] = None) -> bool:
    for trade in _trades:
        if trade.order_id == _order_id and trade.id == _trade_id:
            return False
    return True


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
    def __init__(self, event: events.OrderUpdateWrapper) -> None:
        super().__init__()

        class OriginalOrder:
            def __init__(self, _event: events.OrderUpdateWrapper):
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
        self.remaining_amount = self.amount - self.received_amount
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
        self.step_size = float(_exchange_info_symbol['filters']['lotSize']['stepSize'])
        self.min_notional = float(_exchange_info_symbol['filters']['minNotional']['minNotional'])
        self.tick_size = float(_exchange_info_symbol['filters']['priceFilter']['tickSize'])

    def __call__(self):
        return self

    def round_amount(self, unrounded_amount: float, rounding_type: RoundingType) -> float:
        k = str(format(self.step_size, '.10f')).find('1') - 1
        k = k if k > 0 else 0
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
        k = str(format(self.tick_size, '.10f')).find('1') - 1
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

    def get_min_buy_amount(self, price: float) -> float:
        # print(f"get_min_buy_amount: price:{price}, min_notional:{self.min_notional}")
        return self.round_amount(self.min_notional / price, RoundingType.CEIL)

    def get_minimal_price_change(self, _unused_price: float) -> float:
        return self.tick_size


class Ticker:
    def __init__(self, _ticker):
        # Price of the currency pair one day ago.
        self.last_day_price = float(_ticker.get('openPrice'))
        # Last traded price of the currency pair.
        self.last_price = float(_ticker.get('lastPrice'))
        # Timestamp of the ticker data.
        self.timestamp = int(_ticker.get('closeTime'))
        # print(f'self.last_price: {self.last_price}')

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
        # print(f'self.total_for_currency: {self.total_for_currency}')

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
        # last_state['ms.trades'] = jsonpickle.encode(ms.Strategy.trades)
        last_state['ms.orders'] = jsonpickle.encode(ms.Strategy.orders)
        # print(f"heartbeat.last_state: {last_state}")
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
    cursor_analytic = connection_analytic.cursor()
    delay = HEARTBEAT * 300  # 10 min
    max_use_update = 86400  # 24h if the row has not been updated more than time consider that the asset is not traded
    while True:
        try:
            res = await _stub.FetchAccountInformation(binance_api_pb2.OpenClientConnectionId(client_id=_client_id))
        except asyncio.CancelledError:
            print("save_asset.Cancelled")
        except Exception as _ex:
            ms.Strategy.strategy.message_log(f"Exception save_asset: {_ex}", log_level=LogLevel.WARNING)
        else:
            balances = json_format.MessageToDict(res).get('balances', [])
            # Refresh actual balance
            balance_f = next(item for item in balances if item["asset"] == _base_asset)
            balance_s = next(item for item in balances if item["asset"] == _quote_asset)
            funds = {_base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                     _quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
            ms.Strategy.funds = funds
            # print(f"save_asset: {funds}")
            # Get list of asset without current pair
            assets = {}
            for balance in balances:
                if balance['asset'] not in (_base_asset, _quote_asset):
                    total = float(balance['free']) + float(balance['locked'])
                    if total:
                        assets[balance['asset']] = total
            # Delete all not used and old updated currency from table
            cursor_analytic.execute('DELETE\
                                     FROM t_asset\
                                     WHERE id_exchange=:id_exchange\
                                     and use=:use\
                                     and timestamp<:timestamp',
                                    {'id_exchange': ms.ID_EXCHANGE, 'use': 0, 'timestamp': time.time() - delay})

            cursor_analytic.execute('SELECT id_exchange, currency, value, use, timestamp\
                                     FROM t_asset\
                                     WHERE id_exchange=:id_exchange',
                                    {'id_exchange': ms.ID_EXCHANGE})
            rows = cursor_analytic.fetchall()
            # print(f"save_asset.rows: {rows}")
            for row in rows:
                if row[1] in (_base_asset, _quote_asset):
                    cursor_analytic.execute('UPDATE t_asset SET use=:use, timestamp=:timestamp\
                                             WHERE id_exchange=:id_exchange\
                                             and currency=:currency',
                                            {'use': 1, 'timestamp': time.time(),
                                             'id_exchange': ms.ID_EXCHANGE, 'currency': row[1]})
                else:
                    # Check used currency for last update time
                    if row[3]:
                        # Do not add used currency from other pair
                        if assets.get(row[1]):
                            assets.pop(row[1])
                        if time.time() - row[4] > max_use_update:
                            cursor_analytic.execute('UPDATE t_asset SET use=:use, timestamp=:timestamp\
                                                     WHERE id_exchange=:id_exchange\
                                                     and currency=:currency',
                                                    {'use': 0, 'timestamp': time.time(),
                                                     'id_exchange': ms.ID_EXCHANGE, 'currency': row[1]})
                    else:
                        # Remove not needed asset
                        if time.time() - row[4] < delay and assets.get(row[1]):
                            assets.pop(row[1])
            if assets:
                for key, value in assets.items():
                    cursor_analytic.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                            (ms.ID_EXCHANGE, key, value, 0, int(time.time())))
            connection_analytic.commit()
        await asyncio.sleep(delay)


async def ask_exit(sig_name, _stub, _client_id, _symbol):
    # print(f"ask_exit._strategy: {_strategy}, _loop: {_loop}")
    if ms.Strategy.strategy:
        ms.Strategy.strategy.message_log(f"Got signal {sig_name}: exit", color=ms.Style.MAGENTA)
        await _stub.StopStream(binance_api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol))
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        try:
            ms.Strategy.strategy.stop()
        except Exception as _err:
            print(f"ask_exit.strategy.stop: {_err}")
        ms.Strategy.strategy = None
        if os.path.exists(ms.FILE_LAST_STATE):
            answer = input('Save current state? y/n:')
            if answer.lower() != 'y':
                if os.path.exists(ms.FILE_LAST_STATE + '.bak'):
                    os.remove(ms.FILE_LAST_STATE + '.bak')
                os.rename(ms.FILE_LAST_STATE, ms.FILE_LAST_STATE + '.bak')
                print('Current state cleared')
            else:
                print('OK')
        loop.remove_signal_handler(SIGINT)


async def buffered_candle(_stub, _client_id, _symbol):
    StrategyBase.Klines.klines_lim = KLINES_LIM
    for i in KLINES_INIT:
        res = await _stub.FetchKlines(binance_api_pb2.FetchKlinesRequest(
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
        loop.create_task(on_klines_update(_stub, _client_id, _symbol, i.value, kline_i))


async def on_klines_update(_stub, _client_id, _symbol, _interval, _kline_i):
    # print(f"call on_klines_update: {_interval}")
    async for candle in _stub.OnKlinesUpdate(binance_api_pb2.FetchKlinesRequest(
            client_id=_client_id,
            symbol=_symbol,
            interval=_interval)):
        # print(f"on_klines_update: {candle.symbol}, {candle.interval}")
        # print(json.loads(candle.candle))
        _kline_i.refresh(json.loads(candle.candle))


async def buffered_funds(_stub, _client_id, _symbol, _base_asset, _quote_asset, print_info: bool = True):
    try:
        res = await _stub.FetchAccountInformation(binance_api_pb2.OpenClientConnectionId(
            client_id=_client_id))
    except asyncio.CancelledError:
        print("buffered_funds.Cancelled")
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Exception buffered_funds: {_ex}", log_level=LogLevel.WARNING)
    else:
        balances = json_format.MessageToDict(res).get('balances', [])
        # print(f"buffered_funds.balances: {balances}")
        balance_f = next(item for item in balances if item["asset"] == _base_asset)
        balance_s = next(item for item in balances if item["asset"] == _quote_asset)
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
            _orders = await _stub.FetchOpenOrders(binance_api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol))
            StrategyBase.rate_limiter = max(StrategyBase.rate_limiter, _orders.rate_limiter)
            orders = json_format.MessageToDict(_orders).get('items', [])
            # print(f"buffered_orders.orders: {orders}")
            if orders:
                # print(f"buffered_orders.orders: {orders}")
                for order in orders:
                    all_orders.append(Order(order))
                    exch_orders_id.append(int(order['orderId']))
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
                if diff_id:
                    ms.Strategy.strategy.message_log(f"Perhaps was missed event for order(s): {diff_id}, checking it",
                                                     log_level=LogLevel.WARNING, tlg=True)
                    diff_id_canceled = []
                    for _id in diff_id:
                        check_status = await fetch_order(_id, _filled_update_call=True)
                        if check_status.get('status') and check_status.get('status') == 'CANCELED':
                            diff_id_canceled.append(_id)
                        # Delete from orders list
                        remove_from_orders_lists(diff_id_canceled)
                        diff_id_canceled.clear()
                if diff_excess_id:
                    ms.Strategy.strategy.message_log(f"Find excess order(s): {diff_excess_id}, checking it",
                                                     log_level=LogLevel.WARNING, tlg=True)
                    for _id in diff_excess_id:
                        check_status = await fetch_order(_id, _filled_update_call=False)
                        if check_status.get('status') not in ('FILLED', 'CANCELED'):
                            print("buffered_orders.create_task: cancel_order")
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
                        # ms.Strategy.trades = jsonpickle.decode(last_state.pop('ms.trades', '[]'))
                        # print(f"buffered_orders.ms.trades: {ms.Strategy.trades}")
                        ms.Strategy.orders = jsonpickle.decode(last_state.pop('ms.orders', '[]'))
                        # print(f"buffered_orders.ms.orders: {ms.Strategy.orders}")
                    else:
                        last_state.pop('ms.order_id', None)
                        # last_state.pop('ms.trades', None)
                        last_state.pop('ms.orders', None)
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
                        print(f"Executed order(s) is: {diff_id}")
                        for _id in diff_id:
                            remove_from_trades_lists(_id)
                            for i, o in enumerate(ms.Strategy.orders):
                                if o.id == _id and trade_not_exist(_id, 1, ms.Strategy.trades):
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
            print("buffered_orders.Cancelled")
            run = False
        except Exception as _ex:
            ms.Strategy.strategy.message_log(f"Exception buffered_orders: {_ex}", log_level=LogLevel.WARNING)
            if 'Rate limit reached' in str(_ex):
                StrategyBase.rate_limiter += HEARTBEAT
                ms.Strategy.strategy.message_log(f"RATE_LIMITER set to {StrategyBase.rate_limiter}s",
                                                 log_level=LogLevel.WARNING)
                await asyncio.sleep(ORDER_TIMEOUT)
                await _stub.ResetRateLimit(binance_api_pb2.OpenClientConnectionId(
                                                                                client_id=_client_id,
                                                                                rate_limiter=StrategyBase.rate_limiter))
            else:
                restore = True
                await asyncio.sleep(StrategyBase.rate_limiter)
        await asyncio.sleep(StrategyBase.rate_limiter)


async def on_funds_update(_stub, _client_id, _symbol, _base_asset, _quote_asset):
    async for _funds in _stub.OnFundsUpdate(binance_api_pb2.OnFundsUpdateRequest(
            client_id=_client_id, symbol=_symbol, base_asset=_base_asset, quote_asset=_quote_asset)):
        funds = json.loads(json.loads(json_format.MessageToJson(_funds))['funds'])
        if funds.get(_base_asset) and funds.get(_quote_asset):
            ms.Strategy.funds = funds
            # print(f"on_funds_update.funds: {funds}")
            funds = {_base_asset: FundsEntry(funds[_base_asset]),
                     _quote_asset: FundsEntry(funds[_quote_asset])}
            ms.Strategy.strategy.on_new_funds(funds)
            ms.Strategy.get_buffered_funds_last_time = time.time()


async def on_order_update(_stub, _client_id, _symbol):
    async for event in _stub.OnOrderUpdate(binance_api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol)):
        # Only for registered orders
        # print(f"on_order_update: {event.symbol}:{event.order_id}:{event.order_status}")
        if _symbol == event.symbol and ms.Strategy.order_exist(event.order_id):
            # ms.Strategy.strategy.message_log(f"on_order_update: {event.order_id}, order_status: {event.order_status}",
            #                                  log_level=LogLevel.DEBUG, color=ms.Style.BLUE)
            if event.order_status in ('FILLED', 'PARTIALLY_FILLED'):
                if event.order_status == 'FILLED':
                    # Remove from all_orders and orders lists
                    remove_from_orders_lists([event.order_id])
                if trade_not_exist(event.order_id, event.trade_id, ms.Strategy.trades):
                    trade = {"qty": event.last_executed_quantity,
                             "isBuyer": bool(event.side == 'BUY'),
                             "id": event.trade_id,
                             "orderId": event.order_id,
                             "price": event.last_executed_price,
                             "time": event.transaction_time}
                    # ms.Strategy.strategy.message_log(f"on_order_update.trade: {trade}",
                    #                                  log_level=LogLevel.DEBUG, color=ms.Style.YELLOW)
                    #  Append to all_trades and trades list
                    if len(ms.Strategy.trades) > TRADES_LIST_LIMIT:
                        del ms.Strategy.trades[0]
                    ms.Strategy.trades.append(PrivateTrade(trade))
                    if len(ms.Strategy.all_trades) > ALL_TRADES_LIST_LIMIT:
                        del ms.Strategy.all_trades[0]
                    ms.Strategy.all_trades.append(PrivateTrade(trade))
                    if event.order_status == 'FILLED':
                        # Check if was missed Partially filling event
                        _saved_filled_quantity = 0.0
                        for _trade in ms.Strategy.trades:
                            if _trade.order_id == event.order_id:
                                # print(f"on_order_update: order: {_trade.order_id},"
                                #       f" trade: {_trade.id}: {_trade.amount}")
                                _saved_filled_quantity += _trade.amount
                        saved_filled_quantity = ms.Strategy.tcm.round_amount(_saved_filled_quantity, RoundingType.ROUND)
                        quantity = ms.Strategy.tcm.round_amount(float(event.cumulative_filled_quantity),
                                                                RoundingType.ROUND)
                        # print(f"on_order_update: saved_filled_quantity: {saved_filled_quantity}\n"
                        #       f"event.cumulative_filled_quantity: {quantity}")
                        if saved_filled_quantity < quantity:
                            ms.Strategy.strategy.message_log(f"Order: {event.order_id}"
                                                             f" was missed partially filling event",
                                                             log_level=LogLevel.DEBUG)
                            # Remove trades associated with order from list
                            remove_from_trades_lists(event.order_id)
                            # Update current trade
                            trade.update({"qty": event.cumulative_filled_quantity})
                            # ms.Strategy.strategy.message_log(f"on_order_update.trade: {trade}",
                            #                                  log_level=LogLevel.DEBUG, color=ms.Style.YELLOW)
                            # Append to list
                            ms.Strategy.trades.append(PrivateTrade(trade))
                            ms.Strategy.all_trades.append(PrivateTrade(trade))
                    ms.Strategy.strategy.on_order_update(OrderUpdate(event))


async def create_limit_order(_id: int, buy: bool, amount: str, price: str) -> None:
    try:
        res = await ms.Strategy.stub.CreateLimitOrder(binance_api_pb2.CreateLimitOrderRequest(
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
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Create limit order exception: {_ex}")
    else:
        # ms.Strategy.strategy.message_log(f"create_limit_order.result: {result}",
        #                                  log_level=LogLevel.INFO, color=ms.Style.UNDERLINE)
        ms.Strategy.wait_order_id.append(_id)
        order = Order(result)
        ms.Strategy.strategy.message_log(
            f"Order placed {order.id}({result.get('clientOrderId')}) for {result.get('side')} {order.amount} by "
            f"{order.price} Remaining amount {order.remaining_amount}",
            color=ms.Style.GREEN)
        if order.remaining_amount == 0.0:
            # noinspection PyArgumentList
            trade = {"qty": order.amount,
                     "isBuyer": order.buy,
                     "id": 1,
                     "orderId": order.id,
                     "price": ms.Strategy.get_trading_capability_manager().round_price(
                                  float(result.get('cummulativeQuoteQty')) / order.amount, RoundingType.ROUND),
                     "time": order.timestamp}
            # ms.Strategy.strategy.message_log(f"place_limit_order_callback.trade: {trade}", color=ms.Style.YELLOW)
            if len(ms.Strategy.trades) > TRADES_LIST_LIMIT:
                del ms.Strategy.trades[0]
            ms.Strategy.trades.append(PrivateTrade(trade))
            if len(ms.Strategy.all_trades) > ALL_TRADES_LIST_LIMIT:
                del ms.Strategy.all_trades[0]
            ms.Strategy.all_trades.append(PrivateTrade(trade))
        else:
            ms.Strategy.orders.append(order)
            if not ms.Strategy.all_order_exist(order.id):
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
        res = await ms.Strategy.stub.CancelOrder(binance_api_pb2.CancelOrderRequest(
            client_id=ms.Strategy.client_id,
            symbol=ms.Strategy.symbol,
            order_id=_id))
        result = json_format.MessageToDict(res)
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    except Exception as _ex:
        ms.Strategy.strategy.message_log(f"Exception on cancel order call for {_id}:\n{_ex}")
        await asyncio.sleep(HEARTBEAT)
        if 'Rate limit reached' not in str(_ex):
            check_status = await fetch_order(_id, _filled_update_call=True)
            if check_status.get('status') == 'CANCELED':
                # For stop timeout firing
                ms.Strategy.canceled_order_id.append(_id)
    else:
        # Remove from all_orders and orders lists
        remove_from_orders_lists([_id])
        ms.Strategy.strategy.message_log(f"Cancel order {_id} success", color=ms.Style.GREEN)
        ms.Strategy.strategy.on_cancel_order_success(_id, Order(result))
        await asyncio.sleep(ORDER_TIMEOUT / 3)
        ms.Strategy.canceled_order_id.append(_id)


async def cancel_order_timeout(_id):
    await asyncio.sleep(ORDER_TIMEOUT)
    if _id in ms.Strategy.canceled_order_id:
        ms.Strategy.canceled_order_id.remove(_id)
    else:
        ms.Strategy.strategy.on_cancel_order_error_string(_id, 'Cancel order timeout')


async def fetch_order(_id: int, _filled_update_call: bool = False):
    try:
        res = await ms.Strategy.stub.FetchOrder(binance_api_pb2.FetchOrderRequest(
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
    async for ticker in _stub.OnTickerUpdate(binance_api_pb2.MarketRequest(client_id=_client_id, symbol=_symbol)):
        ticker_24h = {'openPrice': ticker.open_price,
                      'lastPrice': ticker.close_price,
                      'closeTime': ticker.event_time}
        ms.Strategy.ticker = ticker_24h
        ms.Strategy.strategy.on_new_ticker(Ticker(ms.Strategy.ticker))
        # print(f"on_ticker_update: {ticker.symbol} {ms.Strategy.ticker['closeTime']}")


async def on_order_book_update(_stub, _client_id, _symbol):
    async for _order_book in _stub.OnOrderBookUpdate(binance_api_pb2.MarketRequest(client_id=_client_id,
                                                                                   symbol=_symbol)):
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


async def main(_symbol):
    ms.Strategy.symbol = _symbol
    StrategyBase.symbol = _symbol
    # ms.Strategy.loop = loop
    account_name = ms.EXCHANGE[ms.ID_EXCHANGE]
    print(f"main.account_name: {account_name}")
    channel = grpc.aio.insecure_channel(target='localhost:50051', options=CHANNEL_OPTIONS)
    stub = binance_api_pb2_grpc.MartinStub(channel)
    client_id_msg = await stub.OpenClientConnection(binance_api_pb2.OpenClientConnectionRequest(
        account_name=account_name,
        rate_limiter=StrategyBase.rate_limiter))
    print(f"main.client_id: {client_id_msg.client_id}")
    print(f"main.srv_version: {client_id_msg.srv_version}")
    if not client_id_msg.client_id:
        print("Can't get client_id, check configuration settings")
        sys.exit()
    ms.Strategy.stub = stub
    ms.Strategy.client_id = client_id_msg.client_id
    # Check and Cancel ALL ACTIVE ORDER
    _active_orders = await stub.FetchOpenOrders(binance_api_pb2.MarketRequest(client_id=client_id_msg.client_id,
                                                                              symbol=_symbol))
    # print(f"main._active_orders: {_active_orders}")
    active_orders = json_format.MessageToDict(_active_orders).get('items', [])
    # print(f"main.active_orders: {active_orders}")
    restore_state = False
    if os.path.exists(ms.FILE_LAST_STATE):
        restore_state = True
        print(f"main.restore_state: {restore_state}")
        with open(ms.FILE_LAST_STATE) as json_file:
            last_state = json.load(json_file)
        # print(f"main.last_state: {last_state}")
        json_file.close()
        os.remove(ms.FILE_LAST_STATE)
    if CANCEL_ALL_ORDERS and active_orders and not ms.LOAD_LAST_STATE:
        answer = input('Are you want cancel all active order for this pair? Y:')
        if answer.lower() == 'y':
            restore_state = False
            _cancel_orders = await stub.CancelAllOrders(binance_api_pb2.MarketRequest(client_id=client_id_msg.client_id,
                                                                                      symbol=_symbol))
            cancel_orders = json_format.MessageToDict(_active_orders).get('items', [])
            print('Before start cancel orders:')
            for i in cancel_orders:
                print(f"Order:{i['orderId']}, side:{i['side']}, amount:{i['origQty']}, price:{i['price']}")
            print('================================================================')
    # Init section
    _exchange_info_symbol = await stub.FetchExchangeInfoSymbol(binance_api_pb2.MarketRequest(
        client_id=client_id_msg.client_id,
        symbol=_symbol))
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
    await buffered_funds(stub, client_id_msg.client_id, _symbol, base_asset, quote_asset)
    # region Get and processing Order book
    _order_book = await stub.FetchOrderBook(binance_api_pb2.MarketRequest(
        client_id=client_id_msg.client_id,
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
        _price = await stub.FetchSymbolPriceTicker(binance_api_pb2.MarketRequest(
            client_id=client_id_msg.client_id,
            symbol=_symbol))
        price = json_format.MessageToDict(_price)
        print(f"Not bids or asks for pair {price.get('symbol')}, last known price is {price.get('price')}")
        amount = exchange_info_symbol['filters']['lotSize']['minQty']
        order_book['bids'] = order_book['bids'] or [[price['price'], amount]]
        order_book['asks'] = order_book['asks'] or [[price['price'], amount]]
    # print(f"main.order_book: {order_book}")
    ms.Strategy.order_book = order_book
    # endregion
    _ticker = await stub.FetchTickerPriceChangeStatistics(binance_api_pb2.MarketRequest(
        client_id=client_id_msg.client_id,
        symbol=_symbol))
    ms.Strategy.ticker = json_format.MessageToDict(_ticker)
    # print(f"main.ticker: {ms.Strategy.ticker}")
    # init Strategy class
    m_strategy = ms.Strategy()
    # print(f"main.m_strategy: {m_strategy}")
    ms.Strategy.strategy = m_strategy
    await buffered_candle(stub, client_id_msg.client_id, _symbol)
    # Get all trades
    _trades = await stub.FetchAccountTradeList(binance_api_pb2.AccountTradeListRequest(
        client_id=client_id_msg.client_id,
        symbol=_symbol,
        limit=ALL_TRADES_LIST_LIMIT))
    trades = json_format.MessageToDict(_trades).get('items', [])
    # print(f"main.trades: {trades}")
    for trade in trades:
        ms.Strategy.all_trades.append(PrivateTrade(trade))
    # Get all active orders
    loop.create_task(buffered_orders(stub, client_id_msg.client_id, _symbol))
    # Market stream
    loop.create_task(on_ticker_update(stub, client_id_msg.client_id, _symbol))
    loop.create_task(on_order_book_update(stub, client_id_msg.client_id, _symbol))
    # User Stream
    loop.create_task(on_funds_update(stub, client_id_msg.client_id, _symbol, base_asset, quote_asset))
    loop.create_task(on_order_update(stub, client_id_msg.client_id, _symbol))
    # Start section
    loop.add_signal_handler(SIGINT, functools.partial(asyncio.run_coroutine_threadsafe,
                                                      ask_exit(SIGINT, stub, client_id_msg.client_id, _symbol), loop))
    loop.create_task(save_asset(stub, client_id_msg.client_id, base_asset, quote_asset))
    answer = str()
    if restore_state:
        if not ms.LOAD_LAST_STATE:
            answer = input('Restore saved state after restart? Y:')
        if ms.LOAD_LAST_STATE or answer.lower() == 'y':
            ms.Strategy.last_state = last_state
            m_strategy.init(check_funds=False)
    if not restore_state or (not ms.LOAD_LAST_STATE and answer.lower() != 'y'):
        m_strategy.init()
        input('Press Enter for Start or Ctrl-Z for Abort\n')
        m_strategy.start()
    loop.run_in_executor(None, heartbeat)
