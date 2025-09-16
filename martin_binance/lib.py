"""
martin-binance classes and methods definitions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.36"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
import inspect
import logging
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN
from enum import Enum
from pathlib import Path

import numpy as np
import ujson as json
from scipy.optimize import minimize

logger = logging.getLogger('logger')

O_DEC = Decimal()


def tasks_manage(tasks_set: set, coro, name=None, add_done_callback=True):
    _t = asyncio.create_task(coro, name=name or inspect.stack()[1][3])
    tasks_set.add(_t)
    if add_done_callback:
        _t.add_done_callback(tasks_set.discard)


async def tasks_cancel(tasks_set: set, name=None, log_out=True):
    tasks = tasks_set.copy()
    for task in tasks:
        if name and name != task.get_name():
            continue
        task.cancel()
        flag = None
        try:
            await task
        except asyncio.CancelledError:  # NOSONAR
            flag = True
        finally:
            tasks_set.discard(task)
            if log_out:
                logger.info(f"The task {task.get_name()} was cancelled {'by force' if flag else ''}")


def any2str(_x) -> str:
    return f"{_x:.10f}".rstrip('0').rstrip('.')


def f2d(_f: float) -> Decimal:
    return Decimal(str(_f))


def solve(fn, value: Decimal, x: Decimal, **kwargs) -> tuple[Decimal, str]:
    def _fn(_x):
        return abs(float(value) - fn(_x, **kwargs))
    res = minimize(_fn, x0=np.array([float(x)]), method='Nelder-Mead')
    if res.success:
        _res = f2d(res.x[0])
        n = 0
        while f2d(fn(_res, **kwargs)) - value < 0:
            _res += f2d(0.1)
            n += 1
            if n > 200:  # cycle limit check
                return O_DEC, "Number of cycles exceeded"
        return _res, f"{res.message} Number of iterations: {res.nit}, correction: +{n*0.1:.2f}"
    return O_DEC, res.message


def convert_from_minute(m: int) -> str:
    intervals = [
        (1, 3, '1m'),
        (3, 5, '3m'),
        (5, 15, '5m'),
        (15, 30, '15m'),
        (30, 60, '30m'),
        (60, 120, '1h'),
        (120, 240, '2h'),
        (240, 360, '4h'),
        (360, 480, '6h'),
        (480, 720, '8h'),
        (720, 1440, '12h'),
        (1440, 4320, '1d'),
        (4320, 10080, '3d'),
        (10080, 44640, '1w')
    ]

    for start, end, value in intervals:
        if start <= m < end:
            return value
    return '1m'  # Default case


def load_file(name: Path) -> dict:
    _res = {}
    if name.exists():
        try:
            with name.open() as state_file:
                _last_state = json.load(state_file)
        except json.JSONDecodeError as er:
            print(f"Exception on decode last state file: {er}")
        else:
            if _last_state.get('ms_start_time_ms', None):
                _res = _last_state
    return _res


def load_last_state(last_state_file) -> dict:
    res = {}
    if last_state_file.exists():
        res = load_file(last_state_file)
        if not res:
            print("Can't load last state, try load previous saved state")
            res = load_file(last_state_file.with_suffix('.prev'))
        if res:
            with last_state_file.with_suffix('.bak').open(mode='w') as outfile:
                json.dump(res, outfile, sort_keys=True, indent=4, ensure_ascii=False)
    return res


class Style:
    __slots__ = ()

    BLACK: str = '\033[30m'
    RED: str = '\033[31m'
    B_RED: str = '\033[1;31m'
    GREEN: str = '\033[32m'
    YELLOW: str = '\033[33m'
    B_YELLOW: str = "\033[33;1m"
    BLUE: str = '\033[34m'
    MAGENTA: str = '\033[35m'
    CYAN: str = '\033[36m'
    GRAY: str = '\033[37m'
    WHITE: str = '\033[0;37m'
    B_WHITE: str = '\033[1;37m'
    UNDERLINE: str = '\033[4m'
    RESET: str = '\033[0m'

    @classmethod
    def __add__(cls, b):
        return Style() + b


class Orders:
    __slots__ = ("orders_list",)

    def __init__(self):
        self.orders_list = []

    def __iter__(self):
        yield from self.orders_list

    def __len__(self):
        return len(self.orders_list)

    def append_order(self, _id: int, buy: bool, amount: Decimal, price: Decimal):
        self.orders_list.append({'id': _id, 'buy': buy, 'amount': amount, 'price': price})

    def remove(self, _id: int):
        self.orders_list[:] = [i for i in self.orders_list if i['id'] != _id]

    def find_order(self, in_orders: list, place_order_id: int):
        """
        Find equal order in_orders[] and self.orders_list[] where in_orders[].id == place_order_id
        If exist return order: Order
        """
        order = None
        for i in self.orders_list:
            if i['id'] == place_order_id:
                for k, o in enumerate(in_orders):
                    if o.buy == i['buy'] and o.amount == i['amount'] and o.price == i['price']:
                        order = in_orders[k]
                        break
            if order:
                break
        return order

    def get_by_id(self, _id: int) -> dict:
        return next((i for i in self.orders_list if i['id'] == _id), None)

    def exist(self, _id: int) -> bool:
        return any(i['id'] == _id for i in self.orders_list)

    def get(self) -> list:
        """
        Get List of Dict for orders
        :return: []
        """
        return self.orders_list

    def get_id_list(self) -> list:
        """
        Get List of orders id
        :return: []
        """
        return [i['id'] for i in self.orders_list]

    def get_first(self) -> tuple:
        """
        Get first order as tuple
        :return: (id, buy, amount, price)
        """
        return tuple(self.orders_list[0].values())

    def get_last(self) -> tuple:
        """
        Get last order as tuple
        :return: (id, buy, amount, price)
        """
        return tuple(self.orders_list[-1].values())

    def restore(self, order_list: list):
        self.orders_list.clear()
        for i in order_list:
            i_dec = {'id': i.get('id'),
                     'buy': i.get('buy'),
                     'amount': f2d(i.get('amount')),
                     'price': f2d(i.get('price'))}
            self.orders_list.append(i_dec)

    def sort(self, cycle_buy: bool):
        if cycle_buy:
            self.orders_list.sort(key=lambda x: x['price'], reverse=True)
        else:
            self.orders_list.sort(key=lambda x: x['price'], reverse=False)

    def sum_amount(self, cycle_buy: bool) -> Decimal:
        _sum = O_DEC
        for i in self.orders_list:
            _sum += i['amount'] * (i['price'] if cycle_buy else 1)
        return _sum


class PrivateTrade:
    __slots__ = (
        "amount",
        "buy",
        "is_maker",
        "id",
        "order_id",
        "price",
        "commission",
        "commission_asset",
        "timestamp"
    )

    def __init__(self, _trade: dict) -> None:
        self.amount = Decimal(_trade["qty"])
        self.buy = _trade.get('isBuyer', False)
        self.is_maker = _trade.get('isMaker', False)
        self.id = int(_trade["id"])
        self.order_id = int(_trade["orderId"])
        self.price = Decimal(_trade["price"])
        self.commission = Decimal(_trade.get('commission', "0"))
        self.commission_asset = _trade.get('commissionAsset', "")
        self.timestamp = int(_trade["time"])

    def __call__(self):
        return self


class OrderUpdate:
    __slots__ = ("original_order", "resulting_trades", "status", "timestamp", "updated_order")

    class Status(Enum):
        """
        Update status defining what happened to the order since the last update.
        """
        FILLED = 0
        ADAPTED = 1
        CANCELED = 2
        NO_CHANGE = 3
        REAPPEARED = 4
        DISAPPEARED = 5
        OTHER_CHANGE = 6
        PARTIALLY_FILLED = 7
        ADAPTED_AND_FILLED = 8

    ADAPTED = Status.ADAPTED
    ADAPTED_AND_FILLED = Status.ADAPTED_AND_FILLED
    CANCELED = Status.CANCELED
    DISAPPEARED = Status.DISAPPEARED
    FILLED = Status.FILLED
    NO_CHANGE = Status.NO_CHANGE
    OTHER_CHANGE = Status.OTHER_CHANGE
    PARTIALLY_FILLED = Status.PARTIALLY_FILLED
    REAPPEARED = Status.REAPPEARED

    def __init__(self, event: dict, trades: list) -> None:

        class OriginalOrder:
            __slots__ = ("id",)

            def __init__(self, _event: dict):
                self.id = _event['order_id']

        self.original_order = OriginalOrder(event)
        self.resulting_trades = []
        for trade in trades:
            if trade.order_id == event['order_id']:
                self.resulting_trades.append(trade)
        if event['order_status'] == 'FILLED':
            self.status = OrderUpdate.FILLED
        elif event['order_status'] == 'PARTIALLY_FILLED':
            self.status = OrderUpdate.PARTIALLY_FILLED
        elif event['order_status'] == 'CANCELED':
            self.status = OrderUpdate.CANCELED
        else:
            self.status = OrderUpdate.OTHER_CHANGE
        self.timestamp = event['transaction_time']
        self.updated_order = None

    def __call__(self):
        return self


class Order:
    __slots__ = ("amount", "buy", "id", "order_type", "price", "received_amount", "remaining_amount", "timestamp")

    def __init__(self, order: dict):
        self.amount = Decimal(order['origQty'])
        self.buy = order['side'] == 'BUY'
        self.id = int(order['orderId'])
        self.order_type = order['type']
        self.received_amount = Decimal(order['executedQty'])
        cummulative_quote_qty = order.get('cummulativeQuoteQty')
        if self.received_amount > 0 and cummulative_quote_qty:
            self.price = Decimal(cummulative_quote_qty) / self.received_amount
        else:
            self.price = Decimal(order['price'])
        self.remaining_amount = self.amount - self.received_amount
        self.timestamp = int(order.get('transactTime', order.get('time', time.time())))

    def __call__(self):
        return self


class Candle:
    __slots__ = ("min_time", "open", "high", "low", "close", "volume", "max_time", "trade_number", "vwap")

    def __init__(self, _candle: list):
        self.min_time = int(_candle[0])
        self.open = float(_candle[1])
        self.high = float(_candle[2])
        self.low = float(_candle[3])
        self.close = float(_candle[4])
        self.volume = float(_candle[5])
        self.max_time = int(_candle[6])
        self.trade_number = int(_candle[8])
        self.vwap = (float(_candle[7]) / self.volume) if self.volume else self.close

    def __call__(self):
        return self


class TradingCapabilityManager:
    __slots__ = (
        "base_asset_precision",
        "quote_asset_precision",
        "min_qty",
        "max_qty",
        "step_size",
        "min_notional",
        "tick_size",
        "multiplier_up",
        "multiplier_down",
        "min_price",
        "max_price",
    )

    def __init__(self, _exchange_info_symbol):
        self.base_asset_precision = int(_exchange_info_symbol.get('baseAssetPrecision'))
        self.quote_asset_precision = int(_exchange_info_symbol.get('quoteAssetPrecision'))
        self.min_qty = Decimal(_exchange_info_symbol['filters']['lotSize']['minQty'])
        self.max_qty = Decimal(_exchange_info_symbol['filters']['lotSize']['maxQty'])
        self.step_size = Decimal(_exchange_info_symbol['filters']['lotSize']['stepSize'].rstrip('0'))
        self.min_notional = (
                Decimal(_exchange_info_symbol['filters'].get('notional', {}).get('minNotional', '0'))
                or Decimal(_exchange_info_symbol['filters'].get('minNotional', {}).get('minNotional', '0'))
        )
        self.tick_size = Decimal(_exchange_info_symbol['filters']['priceFilter']['tickSize'].rstrip('0'))
        self.min_price = Decimal(_exchange_info_symbol['filters']['priceFilter']['minPrice'])
        self.max_price = Decimal(_exchange_info_symbol['filters']['priceFilter']['maxPrice'])
        self.multiplier_up = Decimal(_exchange_info_symbol['filters']['percentPrice']['multiplierUp'])
        self.multiplier_down = Decimal(_exchange_info_symbol['filters']['percentPrice']['multiplierDown'])

    def __call__(self):
        return self

    def round_amount(self, unrounded_amount: Decimal, rounding_type: str) -> Decimal:
        return unrounded_amount.quantize(self.step_size, rounding=rounding_type)

    def round_price(self, unrounded_price: Decimal, rounding_type: str) -> Decimal:
        return unrounded_price.quantize(self.tick_size, rounding=rounding_type)

    def get_min_sell_amount(self, price: Decimal) -> Decimal:
        return max(self.min_qty, self.round_amount(self.min_notional / price, ROUND_CEILING))

    def get_max_sell_amount(self, _unused_price: Decimal) -> Decimal:
        """
        Returns the maximally possible sell amount that can be placed at a given price.
        """
        return self.max_qty

    def get_min_buy_amount(self, price: Decimal) -> Decimal:
        return max(self.min_qty, self.round_amount(self.min_notional / price, ROUND_CEILING))

    def get_minimal_price_change(self) -> Decimal:
        return self.tick_size

    def get_minimal_amount_change(self) -> Decimal:
        """
        Get the minimal amount change that is possible to use on the exchange.
        """
        return self.step_size

    def get_max_sell_price(self, avg_price: Decimal) -> Decimal:
        return self.round_price(avg_price * self.multiplier_up, ROUND_FLOOR)

    def get_max_price(self) -> Decimal:
        return self.max_price

    def get_min_buy_price(self, avg_price: Decimal) -> Decimal:
        return self.round_price(avg_price * self.multiplier_down, ROUND_CEILING)

    def get_min_price(self) -> Decimal:
        return self.min_price


class Ticker:
    __slots__ = ("last_day_price", "last_price", "timestamp")

    def __init__(self, _ticker):
        self.last_day_price = Decimal(_ticker['openPrice'])
        self.last_price = Decimal(_ticker['lastPrice'])
        self.timestamp = int(_ticker['closeTime'])

    def __call__(self):
        return self


class FundsEntry:
    __slots__ = ("available", "reserved", "total_for_currency")

    def __init__(self, _funds):
        self.available = Decimal(_funds['free'])
        self.reserved = Decimal(_funds['locked'])
        self.total_for_currency = self.available + self.reserved

    def __call__(self):
        return self


class OrderBook:
    __slots__ = ("asks", "bids")

    """
    order_book.bids[0].price
    order_book.asks[0].amount
    """

    def __init__(self, _order_book, _tcm=None) -> None:
        class _OrderBookRow:
            __slots__ = ("price", "amount")

            def __init__(self, _order, _tcm=_tcm) -> None:
                self.price = Decimal(_order[0])
                self.amount = Decimal(_order[1])
                if _tcm:
                    self.price = _tcm.round_price(self.price, ROUND_HALF_EVEN)
                    self.amount = _tcm.round_amount(self.amount, ROUND_HALF_EVEN)

        self.asks = []
        self.bids = []
        self.asks.extend(_OrderBookRow(v) for v in _order_book['asks'])
        self.bids.extend(_OrderBookRow(v) for v in _order_book['bids'])

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
        if new_time >= last_time:
            if new_time == last_time:
                self.kline[-1] = candle
            else:
                self.kline.append(candle)
                if len(self.kline) > self.klines_lim:
                    del self.kline[0]
            self.klines_series[self.interval] = self.kline

    @classmethod
    def get_kline(cls, _interval) -> list:
        return cls.klines_series.get(_interval, [])
