"""
martin-binance classes and methods definitions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.2.1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
import inspect
import logging.handlers
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN
from enum import StrEnum
import orjson
from typing import Any, List, Dict, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(f'logger.{__name__}')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)

O_DEC = Decimal()


def parse_bytes_response(response: Any) -> List[dict]:
    return [orjson.loads(item) for item in getattr(response, 'items', [])]


def tasks_manage(tasks_set: set, coro, name=None, add_done_callback=True):
    name = f"{name if name else ''}{'-' if name else ''}{coro.__name__}-{inspect.stack()[1][3]}"
    _t = asyncio.create_task(coro, name=name)
    tasks_set.add(_t)
    if add_done_callback:
        _t.add_done_callback(tasks_set.discard)


async def tasks_cancel(tasks_set: set, name=None, log_out=True):
    tasks = tasks_set.copy()
    for task in tasks:
        task_name = task.get_name()
        if log_out:
            logger.debug(f"Active background task: {task_name}")
        if name and f"{name}" not in task_name:
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
                logger.info(f"The task {task_name} was cancelled {'by force' if flag else ''}")


def task_active(tasks_set: set, name: str) -> bool:
    return any(name in task.get_name() for task in tasks_set)


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
    __slots__ = ("order_id", "resulting_trades", "status", "timestamp", "updated_order")

    class Status(StrEnum):
        FILLED = "FILLED"
        ADAPTED = "ADAPTED"
        CANCELED = "CANCELED"
        NO_CHANGE = "NO_CHANGE"
        REAPPEARED = "REAPPEARED"
        DISAPPEARED = "DISAPPEARED"
        OTHER_CHANGE = "OTHER_CHANGE"
        PARTIALLY_FILLED = "PARTIALLY_FILLED"
        ADAPTED_AND_FILLED = "ADAPTED_AND_FILLED"

    def __init__(self, event: dict, trades: list) -> None:
        self.order_id = event['order_id']
        self.timestamp = event['transaction_time']
        self.resulting_trades = [t for t in trades if t.order_id == self.order_id]
        try:
            self.status = self.Status(event['order_status'])
        except ValueError:
            self.status = self.Status.OTHER_CHANGE

    def __call__(self):
        return self


class Order:
    __slots__ = ("amount", "buy", "id", "order_type", "price", "received_amount", "remaining_amount", "timestamp")

    def __init__(self, order: dict):
        if 'amount' in order and 'origQty' not in order:
            self.id = int(order['id'])
            self.buy = bool(order['buy'])
            self.amount = f2d(order['amount'])
            self.order_type = order.get('order_type', 'LIMIT')
            self.received_amount = f2d(order.get('received_amount', 0))
            self.price = f2d(order['price'])
            self.remaining_amount = f2d(order.get('remaining_amount', self.amount))
            self.timestamp = int(order.get('timestamp', time.time() * 1000))
            return
        self.id = int(order['orderId'])
        self.buy = order['side'] == 'BUY'
        self.amount = f2d(order['origQty'])
        self.order_type = order['type']
        self.received_amount = f2d(order['executedQty'])
        cummulative_quote_qty = order.get('cummulativeQuoteQty')
        if self.received_amount > 0 and cummulative_quote_qty:
            self.price = f2d(cummulative_quote_qty) / self.received_amount
        else:
            self.price = f2d(order['price'])

        self.remaining_amount = self.amount - self.received_amount
        self.timestamp = int(order.get('transactTime', order.get('time', time.time() * 1000)))

    def __call__(self):
        return self


class Orders:
    __slots__ = ("_orders", "tp_order_id",)

    def __init__(self):
        self._orders: Dict[int, Order] = {}
        self.tp_order_id: Optional[int] = None

    def __iter__(self):
        yield from self._orders.values()

    def __len__(self) -> int:
        return len(self._orders) - bool(self.tp_order_id)

    def keys(self, delay: int = 0):
        if not delay:
            return self._orders.keys()
        current_time_ms = int(time.time() * 1000)
        return {
            order_id
            for order_id, order in self._orders.items()
            if (current_time_ms - order.timestamp) >= delay
        }

    def get_counts_by_side(self) -> Tuple[int, int]:
        buy_count = 0
        sell_count = 0
        for o in self._orders.values():
            if o.buy:
                buy_count += 1
            else:
                sell_count += 1
        return buy_count, sell_count

    def clear(self):
        self._orders.clear()

    def update(self, order: Order) -> None:
        self._orders[order.id] = order

    def extend(self, orders: Dict[int, Order]):
        self._orders |= orders

    def append_order(self, _id: int, buy: bool, amount: Decimal, price: Decimal) -> None:
        """Creates and adds an Order object directly to the pool"""
        order_data = {'id': _id, 'buy': buy, 'amount': amount, 'price': price}
        self._orders[_id] = Order(order_data)

    def add_raw_order(self, order: dict) -> Order:
        """Adds an order directly from the raw exchange response"""
        new_order = Order(order)
        self._orders[new_order.id] = new_order
        return new_order

    def remove(self, _id: int | str) -> None:
        """Removes an order from the pool by ID"""
        if self.tp_order_id == int(_id):
            self.tp_order_id = None
        self._orders.pop(int(_id), None)

    def remove_ids(self, _ids: List[int]) -> None:
        """Removes an orders from the pool by IDs"""
        [self._orders.pop(o, None) for o in _ids]  # skipcq: PYL-W0106

    def exist(self, _id: int | str) -> bool:
        return int(_id) in self._orders

    def exist_grid(self, _id: int | str) -> bool:
        return int(_id) != self.tp_order_id and int(_id) in self._orders

    def exist_grids(self) -> bool:
        return bool(len(self._orders) - bool(self.tp_order_id))

    def get_by_id(self, _id: int) -> Optional[Order]:
        """Returns a full-fledged Order object"""
        return self._orders.get(_id)

    def get_id_list(self) -> List[int]:
        return list(self._orders.keys())

    def get(self) -> Dict[int, Order]:
        return self._orders

    def get_list(self) -> List[dict]:
        """Returns a list of old flat dictionaries (for compatibility with legacy code)"""
        return [{'id': o.id, 'buy': o.buy, 'amount': o.amount, 'price': o.price} for o in self._orders.values()]

    def find_order(self, in_orders: List[Order], place_order_id: int) -> Optional[Order]:
        """Searches for an equivalent order in the external list"""
        local = self._orders.get(place_order_id)
        if not local:
            return None

        l_buy, l_amount, l_price = local.buy, local.amount, local.price
        return next((o for o in in_orders if o.buy == l_buy and o.amount == l_amount and o.price == l_price), None)

    def get_first(self) -> Optional[Order]:
        items = self._orders.items()
        return next((order for k, order in items if k != self.tp_order_id), None)

    def get_last(self) -> Optional[Order]:
        reversed_items = reversed(self._orders.items())
        return next((order for k, order in reversed_items if k != self.tp_order_id), None)

    def restore(self, order_list: list):
        """Restores the entire grid from a saved state"""
        self._orders.clear()
        for i in order_list:
            new_order = Order(i)
            self._orders[new_order.id] = new_order

    def sort(self, cycle_buy: bool) -> None:
        """Sorts the internal dictionary by order price"""
        sorted_items = sorted(
            self._orders.items(),
            key=lambda item: item[1].price,
            reverse=cycle_buy
        )
        self._orders = dict(sorted_items)

    def p_filled(self, _id: int | str) -> bool:
        """Check if order partially or fulfilled"""
        if order := self.get_by_id(int(_id)):
            return bool(order.remaining_amount == 0 or order.amount > order.received_amount > 0)
        return False

    def sum_amount(self, cycle_buy: bool) -> Decimal:
        """Efficient mesh volume calculation directly from objects"""
        if cycle_buy:
            return sum((o.amount * o.price for o in self._orders.values()), Decimal('0'))
        return sum((o.amount for o in self._orders.values()), Decimal('0'))


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
