"""
Cyclic grid strategy based on martingale
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.0.4b4"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################
import sys
import gc
import statistics
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING
from threading import Thread
import queue
import math
import sqlite3
from pathlib import Path
import simplejson as json
from datetime import datetime
import os
import psutil
import numpy as np
from scipy.optimize import minimize

from martin_binance import DB_FILE
from martin_binance.db_utils import db_management, save_to_db
from martin_binance.margin_wrapper import __version__ as msb_ver, any2str, Dict, LogLevel, StrategyConfig
from martin_binance.margin_wrapper import StrategyBase, Style, OrderUpdate, Ticker, OrderBook, FundsEntry, Order
from martin_binance.telegram_utils import telegram

O_DEC = Decimal()

# region SetParameters
SYMBOL = str()
EXCHANGE = ()
# Exchange setup
ID_EXCHANGE = int()
FEE_IN_PAIR = bool()
FEE_MAKER = Decimal()
FEE_TAKER = Decimal()
FEE_SECOND = bool()
FEE_BNB_IN_PAIR = bool()
GRID_MAX_COUNT = int()
# Trade parameter
START_ON_BUY = bool()
AMOUNT_FIRST = Decimal()
USE_ALL_FUND = bool()
AMOUNT_SECOND = Decimal()
PRICE_SHIFT = Decimal()
PRICE_LIMIT_RULES = Decimal()
# Round pattern
ROUND_BASE = str()
ROUND_QUOTE = str()
#
PROFIT = Decimal()
PROFIT_MAX = Decimal()
OVER_PRICE = Decimal()
ORDER_Q = int()
MARTIN = Decimal()
SHIFT_GRID_DELAY = int()
GRID_UPDATE_INTERVAL = 60 * 60  # sec between grid update in Reverse cycle
# Other
STATUS_DELAY = int()
GRID_ONLY = bool()
LOG_LEVEL_NO_PRINT = []
HOLD_TP_ORDER_TIMEOUT = 30
COLLECT_ASSETS = bool()
SAVE_TRADE_HISTORY = True
#
ADAPTIVE_TRADE_CONDITION = bool()
BB_CANDLE_SIZE_IN_MINUTES = int()
BB_NUMBER_OF_CANDLES = int()
KBB = float()
#
LINEAR_GRID_K = int()
#
ADX_CANDLE_SIZE_IN_MINUTES = int()
ADX_NUMBER_OF_CANDLES = int()
ADX_PERIOD = int()
ADX_THRESHOLD = int()
ADX_PRICE_THRESHOLD = float()
# Reverse cycle
REVERSE = bool()
REVERSE_TARGET_AMOUNT = Decimal()
REVERSE_INIT_AMOUNT = Decimal()
REVERSE_STOP = bool()
# Config variables
HEAD_VERSION = str()
LOAD_LAST_STATE = int()
# Path and files name
LAST_STATE_FILE: Path
VPS_NAME = str()
PARAMS: Path
# Telegram
TELEGRAM_URL = str()
TOKEN = str()
CHANNEL_ID = str()
STOP_TLG = 'stop_signal_QWE#@!'
INLINE_BOT = True
# Backtesting
MODE = 'T'  # 'T' - Trade, 'TC' - Trade and Collect, 'S' - Simulate
XTIME = 1000  # Time accelerator
SAVE_DS = True  # Save session result data (ticker, orders) for compare
SAVE_PERIOD = 1 * 60 * 60  # sec, timetable for save data portion, but memory limitation consider also matter
SAVED_STATE = False  # Use saved state for backtesting
# endregion


def f2d(_f: float) -> Decimal:
    return Decimal(str(_f))


def solve(fn, value: Decimal, x: Decimal, **kwargs) -> (Decimal, str):
    def _fn(_x):
        return abs(float(value) - fn(_x, **kwargs))
    res = minimize(_fn, x0=np.array([float(x)]), method='Nelder-Mead')
    if res.success:
        return f2d(res.x[0]), f"{res.message} Number of iterations: {res.nit}"
    return O_DEC, res.message


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

    def find_order(self, in_orders: [], place_order_id: int):
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

    def get_by_id(self, _id: int) -> {}:
        return next((i for i in self.orders_list if i['id'] == _id), None)

    def exist(self, _id: int) -> bool:
        return any(i['id'] == _id for i in self.orders_list)

    def get(self) -> []:
        """
        Get List of Dict for orders
        :return: []
        """
        return self.orders_list

    def get_id_list(self) -> []:
        """
        Get List of orders id
        :return: []
        """
        return [i['id'] for i in self.orders_list]

    def get_first(self) -> ():
        """
        Get first order as tuple
        :return: (id, buy, amount, price)
        """
        return tuple(self.orders_list[0].values())

    def get_last(self) -> ():
        """
        Get last order as tuple
        :return: (id, buy, amount, price)
        """
        return tuple(self.orders_list[-1].values())

    def restore(self, order_list: []):
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


class Strategy(StrategyBase):
    ##############################################################
    # strategy control methods
    ##############################################################
    __slots__ = (
        "cycle_buy",
        "orders_grid",
        "orders_init",
        "orders_hold",
        "orders_save",
        # Take profit variables
        "tp_order_id",
        "tp_wait_id",
        "tp_order",
        "tp_error",
        "tp_order_hold",
        "tp_hold",
        "tp_cancel",
        "tp_cancel_from_grid_handler",
        "tp_hold_additional",
        "tp_target",
        "tp_amount",
        "part_profit_first",
        "part_profit_second",
        "tp_was_filled",
        "tp_part_amount_first",
        "tp_part_amount_second",
        #
        "sum_amount_first",
        "sum_amount_second",
        #
        "deposit_first",
        "deposit_second",
        "sum_profit_first",
        "sum_profit_second",
        "cycle_buy_count",
        "cycle_sell_count",
        "shift_grid_threshold",
        "f_currency",
        "s_currency",
        "connection_analytic",
        "last_shift_time",
        "avg_rate",
        #
        "grid_hold",
        "start_hold",
        "initial_first",
        "initial_second",
        "initial_reverse_first",
        "initial_reverse_second",
        "wait_refunding_for_start",
        #
        "cancel_order_id",
        "cancel_grid_order_id",
        "over_price",
        "grid_place_flag",
        "part_amount",
        "command",
        "start_after_shift",
        "queue_to_db",
        "pr_db",
        "pr_tlg",
        "pr_tlg_control",
        "restart",
        "profit_first",
        "profit_second",
        "cycle_time",
        "cycle_time_reverse",
        "reverse",
        "reverse_target_amount",
        "reverse_init_amount",
        "reverse_hold",
        "reverse_price",
        "round_base",
        "round_quote",
        "order_q",
        "order_q_placed",
        "martin",
        "first_run",
        "grid_remove",
        "heartbeat_counter",
        "cycle_status",
        "grid_update_started",
        "start_reverse_time",
        "last_ticker_update",
        "grid_only_restart",
        "wait_wss_refresh",
        "start_collect",
        "restore_orders",
        "ts_grid_update",
        "tp_part_free",
    )

    def __init__(self):
        super().__init__()
        print(f"Init Strategy, ver: {HEAD_VERSION} + {__version__} + {msb_ver}")
        self.cycle_buy = not START_ON_BUY if REVERSE else START_ON_BUY  # + Direction (Buy/Sell) for current cycle
        self.orders_grid = Orders()  # + List of grid orders
        self.orders_init = Orders()  # - List of initial grid orders
        self.orders_hold = Orders()  # + List of grid orders for later place
        self.orders_save = Orders()  # + Save for the time of cancellation
        # Take profit variables
        self.tp_order_id = None  # + Take profit order id
        self.tp_wait_id = None  # -
        self.tp_order = ()  # - (id, buy, amount, price, local_time()) Placed take profit order
        self.tp_error = False  # Flag when can't place tp
        self.tp_order_hold = {}  # - Save unreleased take profit order
        self.tp_hold = False  # - Flag for replace take profit order
        self.tp_cancel = False  # - Wanted cancel tp order after successes place and Start()
        self.tp_cancel_from_grid_handler = False  # -
        self.tp_hold_additional = False  # - Need place TP after placed additional grid orders
        self.tp_target = O_DEC  # + Target amount for TP that will be placed
        self.tp_amount = O_DEC  # + Initial depo for active TP
        self.part_profit_first = O_DEC  # +
        self.part_profit_second = O_DEC  # +
        self.tp_was_filled = ()  # - Exist incomplete processing filled TP
        self.tp_part_amount_first = O_DEC  # + Sum partially filled TP
        self.tp_part_amount_second = O_DEC  # + Sum partially filled TP
        #
        self.sum_amount_first = O_DEC  # Sum buy/sell in first currency for current cycle
        self.sum_amount_second = O_DEC  # Sum buy/sell in second currency for current cycle
        #
        self.deposit_first = AMOUNT_FIRST  # + Calculated operational deposit
        self.deposit_second = AMOUNT_SECOND  # + Calculated operational deposit
        self.sum_profit_first = O_DEC  # + Sum profit from start to now()
        self.sum_profit_second = O_DEC  # + Sum profit from start to now()
        self.cycle_buy_count = 0  # + Count for buy cycle
        self.cycle_sell_count = 0  # + Count for sale cycle
        self.shift_grid_threshold = None  # - Price level of shift grid threshold for current cycle
        self.f_currency = ''  # - First currency name
        self.s_currency = ''  # - Second currency name
        self.connection_analytic = None  # - Connection to .db
        self.last_shift_time = None  # +
        self.avg_rate = O_DEC  # - Flow average rate for trading pair
        #
        self.grid_hold = {}  # - Save for later create grid orders
        self.start_hold = False  # - Hold start if exist not accepted grid order(s)
        self.initial_first = O_DEC  # + Use if balance replenishment delay
        self.initial_second = O_DEC  # + Use if balance replenishment delay
        self.initial_reverse_first = O_DEC  # + Use if balance replenishment delay
        self.initial_reverse_second = O_DEC  # + Use if balance replenishment delay
        self.wait_refunding_for_start = False  # -
        #
        self.cancel_order_id = None  # - Exist canceled not confirmed order
        self.cancel_grid_order_id = None  # - id individual canceled grid order
        self.over_price = None  # + Adaptive over price
        self.grid_place_flag = False  # - Flag when placed next part of grid orders
        self.part_amount = {}  # + {order_id: (Decimal(str(amount_f)), Decimal(str(amount_s)))} of partially filled
        self.command = None  # + External input command from Telegram
        self.start_after_shift = False  # - Flag set before shift, clear after place grid
        self.queue_to_db = queue.Queue()  # - Queue for save data to .db
        self.pr_db = None  # - Process for save data to .db
        self.pr_tlg = None  # - Process for sending message to Telegram
        self.pr_tlg_control = None  # - Process for get command from Telegram
        self.restart = None  # - Set after execute take profit order and restart cycle
        self.profit_first = O_DEC  # + Cycle profit
        self.profit_second = O_DEC  # + Cycle profit
        self.cycle_time = None  # + Cycle start time
        self.cycle_time_reverse = None  # + Reverse cycle start time
        self.reverse = REVERSE  # + Current cycle is Reverse
        self.reverse_target_amount = REVERSE_TARGET_AMOUNT if REVERSE else O_DEC  # + Amount for reverse cycle
        self.reverse_init_amount = REVERSE_INIT_AMOUNT if REVERSE else O_DEC  # + Actual amount of initial cycle
        self.reverse_hold = False  # + Exist unreleased reverse state
        self.reverse_price = None  # + Price when execute last grid order and hold reverse cycle
        self.round_base = '1.0123456789'  # - Round pattern for 0.00000 = 0.00
        self.round_quote = '1.0123456789'  # - Round pattern for 0.00000 = 0.00
        self.order_q = None  # + Adaptive order quantity
        self.order_q_placed = False  # - Flag initial number of orders placed
        self.martin = Decimal(0)  # + Operational increment volume of orders in the grid
        self.first_run = True  # -
        self.grid_remove = None  # - Flag when starting cancel grid orders
        self.heartbeat_counter = 0  # -
        self.cycle_status = ()  # - Operational status for current cycle, orders count
        self.grid_update_started = None  # - Flag when grid update process started
        self.start_reverse_time = None  # -
        self.last_ticker_update = 0  # -
        self.grid_only_restart = None  # -
        self.wait_wss_refresh = {}  # -
        self.start_collect = None
        self.restore_orders = False  # + Flag when was filled grid order during grid cancellation
        self.ts_grid_update = self.get_time()  # - When updated grid
        self.tp_part_free = False  # + Can use TP part amount for converting to grid orders

    def init(self, check_funds: bool = True) -> None:  # skipcq: PYL-W0221
        self.message_log('Start Init section')
        if not FEE_IN_PAIR and FEE_SECOND:
            init_params_error = 'FEE_IN_PAIR and FEE_SECOND'
        elif not FEE_IN_PAIR and FEE_BNB_IN_PAIR:
            init_params_error = 'FEE_IN_PAIR and FEE_BNB_IN_PAIR'
        elif COLLECT_ASSETS and GRID_ONLY:
            init_params_error = 'COLLECT_ASSETS and GRID_ONLY: one only allowed'
        elif PROFIT_MAX and PROFIT_MAX < PROFIT + FEE_TAKER:
            init_params_error = 'PROFIT_MAX'
        else:
            init_params_error = None
        if init_params_error:
            self.message_log(f"Incorrect value for {init_params_error}", log_level=LogLevel.ERROR)
            raise SystemExit(1)
        db_management(EXCHANGE)
        tcm = self.get_trading_capability_manager()
        self.f_currency = self.get_first_currency()
        self.s_currency = self.get_second_currency()
        self.tlg_header = f"{EXCHANGE[ID_EXCHANGE]}, {self.f_currency}/{self.s_currency}. "
        self.message_log(f"{self.tlg_header}", color=Style.B_WHITE)
        self.status_time = int(self.get_time())
        self.start_after_shift = True
        self.over_price = OVER_PRICE
        self.order_q = ORDER_Q
        self.martin = (MARTIN + 100) / 100
        if not check_funds:
            self.first_run = False
        if GRID_ONLY:
            self.message_log(f"Mode for {'Buy' if self.cycle_buy else 'Sell'} {self.f_currency} by grid orders"
                             f" placement ON",
                             color=Style.B_WHITE)
        self.message_log(f"This is {'Trade' if MODE == 'T' else ('Trade & Collect' if MODE == 'TC' else 'Simulate')}"
                         f" mode",
                         color=Style.B_WHITE if MODE == 'T' else (Style.B_RED if MODE == 'TC' else Style.GREEN))
        # Calculate round float multiplier
        self.round_base = ROUND_BASE or str(tcm.round_amount(f2d(1.123456789), ROUND_FLOOR))
        self.round_quote = ROUND_QUOTE or str(Decimal(self.round_base) *
                                              Decimal(str(tcm.round_price(f2d(1.123456789), ROUND_FLOOR))))
        self.message_log(f"Round pattern, for base: {self.round_base}, quote: {self.round_quote}")
        if last_price := self.get_buffered_ticker().last_price:
            self.message_log(f"Last ticker price: {last_price}")
            self.avg_rate = last_price
            if self.first_run and check_funds:
                if self.cycle_buy:
                    ds = self.get_buffered_funds().get(self.s_currency, O_DEC)
                    ds = ds.available if ds else O_DEC
                    if USE_ALL_FUND:
                        self.deposit_second = self.round_truncate(ds, base=False)
                    elif self.deposit_second > ds:
                        self.message_log('Not enough second coin for Buy cycle!', color=Style.B_RED)
                        raise SystemExit(1)
                else:
                    df = self.get_buffered_funds().get(self.f_currency, O_DEC)
                    df = df.available if df else O_DEC
                    if USE_ALL_FUND:
                        self.deposit_first = self.round_truncate(df, base=True)
                    elif self.deposit_first > df:
                        self.message_log('Not enough first coin for Sell cycle!', color=Style.B_RED)
                        raise SystemExit(1)
        else:
            self.message_log("Can't get actual price, initialization checks stopped", log_level=LogLevel.CRITICAL)
            raise SystemExit(1)
        # self.message_log('End Init section')

    @staticmethod
    def get_strategy_config() -> StrategyConfig:
        s = StrategyConfig()
        s.required_data_updates = {StrategyConfig.ORDER_BOOK,
                                   StrategyConfig.FUNDS,
                                   StrategyConfig.TICKER}
        s.normalize_exchange_buy_amounts = True
        return s

    def save_strategy_state(self, return_only=False) -> Dict[str, str]:
        if not return_only:
            # region SaveOperationalStatus
            # Skip when transition processes or GRID_ONLY mode
            stable_state = (self.shift_grid_threshold is None
                            and self.grid_remove is None
                            and not self.reverse_hold
                            and not GRID_ONLY
                            and not self.grid_update_started
                            and not self.start_after_shift
                            and not self.tp_hold
                            and not self.tp_was_filled
                            and not self.orders_init)
            if (MODE in ('T', 'TC') and (stable_state or (self.grid_hold.get('timestamp') and
                int(self.get_time() - self.grid_hold['timestamp']) > HOLD_TP_ORDER_TIMEOUT) or
                    (self.tp_order_hold.get('timestamp') and
                     int(self.get_time() - self.tp_order_hold['timestamp']) > HOLD_TP_ORDER_TIMEOUT))):
                orders = self.get_buffered_open_orders()
                order_buy = len([i for i in orders if i.buy is True])
                order_sell = len([i for i in orders if i.buy is False])
                order_hold = len(self.orders_hold)
                cycle_status = (self.cycle_buy, order_buy, order_sell, order_hold)
                if self.cycle_status != cycle_status:
                    self.cycle_status = cycle_status
                    data_to_db = {
                        'ID_EXCHANGE': ID_EXCHANGE,
                        'f_currency': self.f_currency,
                        's_currency': self.s_currency,
                        'cycle_buy': self.cycle_buy,
                        'order_buy': order_buy,
                        'order_sell': order_sell,
                        'order_hold': order_hold,
                        'destination': 't_orders'
                    }
                    if self.queue_to_db:
                        # print('Send data to t_orders')
                        self.queue_to_db.put(data_to_db)
            else:
                self.cycle_status = ()
            # endregion
            # region ReportStatus
            # Get command from Telegram
            command = None
            if MODE in ('T', 'TC') and self.connection_analytic and self.heartbeat_counter % 5 == 0:
                cursor_analytic = self.connection_analytic.cursor()
                bot_id = self.tlg_header.split('.')[0]
                try:
                    cursor_analytic.execute('SELECT max(message_id), text_in, bot_id\
                                            FROM t_control WHERE bot_id=:bot_id', {'bot_id': bot_id})
                    row = cursor_analytic.fetchone()
                    cursor_analytic.close()
                except sqlite3.Error as err:
                    cursor_analytic.close()
                    row = None
                    print(f"SELECT from t_control: {err}")
                if row and row[0]:
                    # Analyse and execute received command
                    command = row[1]
                    if command != 'status':
                        self.command = command
                        command = None
                    # Remove applied command from .db
                    try:
                        self.connection_analytic.execute('UPDATE t_control SET apply = 1 WHERE message_id=:message_id',
                                                         {'message_id': row[0]})
                        self.connection_analytic.commit()
                    except sqlite3.Error as err:
                        print(f"UPDATE t_control: {err}")
                # self.message_log(f"save_strategy_state.command: {self.command}", log_level=LogLevel.DEBUG)
            if self.command == 'stopped':
                if isinstance(self.start_collect, int):
                    if self.start_collect < 5:
                        self.start_collect += 1
                    else:
                        self.start_collect = False
            elif self.command == 'restart':
                self.stop()
                os.execv(sys.executable, [sys.executable] + [sys.argv[0]] + ['1'])
            if (MODE in ('T', 'TC') and
                    (command or (STATUS_DELAY and (self.get_time() - self.status_time) / 60 > STATUS_DELAY))):
                # Report current status
                last_price = self.get_buffered_ticker().last_price
                ticker_update = int(self.get_time()) - self.last_ticker_update
                if self.cycle_time:
                    ct = str(datetime.utcnow() - self.cycle_time).rsplit('.')[0]
                else:
                    self.message_log("save_strategy_state: cycle_time is None!", log_level=LogLevel.DEBUG)
                    ct = str(datetime.utcnow()).rsplit('.')[0]
                if self.command == 'stopped':
                    self.message_log("Strategy stopped. Need manual action", tlg=True)
                elif self.grid_hold or self.tp_order_hold:
                    funds = self.get_buffered_funds()
                    fund_f = funds.get(self.f_currency, O_DEC)
                    fund_f = fund_f.available if fund_f else O_DEC
                    fund_s = funds.get(self.s_currency, O_DEC)
                    fund_s = fund_s.available if fund_s else O_DEC
                    if self.grid_hold.get('timestamp'):
                        time_diff = int(self.get_time() - self.grid_hold['timestamp'])
                        self.message_log(f"Exist unreleased grid orders for\n"
                                         f"{'Buy' if self.cycle_buy else 'Sell'} cycle with"
                                         f" {self.grid_hold['depo']}"
                                         f" {self.s_currency if self.cycle_buy else self.f_currency} depo.\n"
                                         f"Available first: {fund_f} {self.f_currency}\n"
                                         f"Available second: {fund_s} {self.s_currency}\n"
                                         f"Last ticker price: {last_price}\n"
                                         f"WSS status: {ticker_update}s\n"
                                         f"From start {ct}\n"
                                         f"Delay: {time_diff} sec", tlg=True)
                    elif self.tp_order_hold.get('timestamp'):
                        time_diff = int(self.get_time() - self.tp_order_hold['timestamp'])
                        if time_diff > HOLD_TP_ORDER_TIMEOUT:
                            self.message_log(f"Exist hold TP order for"
                                             f" {'Sell' if self.cycle_buy else 'Buy'} {self.tp_order_hold['amount']}"
                                             f" {self.f_currency if self.cycle_buy else self.s_currency}\n"
                                             f"Available first:{fund_f} {self.f_currency}\n"
                                             f"Available second:{fund_s} {self.s_currency}\n"
                                             f"Last ticker price: {last_price}\n"
                                             f"WSS status: {ticker_update}s\n"
                                             f"From start {ct}\n"
                                             f"Delay: {time_diff} sec", tlg=True)
                else:
                    if self.cycle_status:
                        order_buy = self.cycle_status[1]
                        order_sell = self.cycle_status[2]
                        order_hold = self.cycle_status[3]
                    else:
                        orders = self.get_buffered_open_orders()
                        order_buy = len([i for i in orders if i.buy is True])
                        order_sell = len([i for i in orders if i.buy is False])
                        order_hold = len(self.orders_hold)
                    sum_profit = self.round_truncate(self.sum_profit_first * self.avg_rate + self.sum_profit_second,
                                                     base=False)
                    command = bool(self.command in ('end', 'stop'))
                    if GRID_ONLY:
                        header = (f"{'Buy' if self.cycle_buy else 'Sell'} assets Grid only mode\n"
                                  f"{('Waiting funding for convert'+chr(10)) if self.grid_only_restart else ''}"
                                  f"{self.get_free_assets()[3]}"
                                  )
                    else:
                        header = (f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                                  f"For all cycles profit:\n"
                                  f"First: {self.sum_profit_first}\n"
                                  f"Second: {self.sum_profit_second}\n"
                                  f"Summary: {sum_profit}\n"
                                  f"{self.get_free_assets(mode='free')[3]}"
                                  )
                    self.message_log(f"{header}\n"
                                     f"{'*** Shift grid mode ***' if self.shift_grid_threshold else '* **  **  ** *'}\n"
                                     f"{'Buy' if self.cycle_buy else 'Sell'}{' Reverse' if self.reverse else ''}"
                                     f"{' Hold reverse' if self.reverse_hold else ''} cycle with"
                                     f" {order_buy} buy and {order_sell} sell active orders.\n"
                                     f"{order_hold or 'No'} hold grid orders\n"
                                     f"Over price: {self.over_price:.2f}%\n"
                                     f"Last ticker price: {last_price}\n"
                                     f"ver: {HEAD_VERSION}+{__version__}+{msb_ver}\n"
                                     f"From start {ct}\n"
                                     f"WSS status: {ticker_update}s\n"
                                     f"{'-   ***   ***   ***   -' if self.command == 'stop' else ''}\n"
                                     f"{'Waiting for end of cycle for manual action' if command else ''}",
                                     tlg=True)
            # endregion
            # region ProcessingEvent
            if self.wait_wss_refresh and self.get_time() - self.wait_wss_refresh['timestamp'] > SHIFT_GRID_DELAY:
                self.place_grid(self.wait_wss_refresh['buy_side'],
                                self.wait_wss_refresh['depo'],
                                self.reverse_target_amount,
                                self.wait_wss_refresh['allow_grid_shift'],
                                self.wait_wss_refresh['additional_grid'],
                                self.wait_wss_refresh['grid_update'])
            self.heartbeat_counter += 1
            if ADAPTIVE_TRADE_CONDITION and stable_state and self.command != 'stopped':
                if self.tp_order_id and not self.tp_part_amount_first and self.get_time() - self.tp_order[3] > 60*15:
                    self.message_log("Update TP order", color=Style.B_WHITE)
                    self.place_profit_order()
                elif self.heartbeat_counter % 15 == 0 \
                        and (self.orders_grid or self.orders_hold) and not self.part_amount:
                    self.grid_update()
            if self.heartbeat_counter > 150:
                self.heartbeat_counter = 0
                if MODE in ('T', 'TC') and not GRID_ONLY:
                    # Update t_funds.active set True
                    data_to_db = {
                        'ID_EXCHANGE': ID_EXCHANGE,
                        'f_currency': self.f_currency,
                        's_currency': self.s_currency,
                        'destination': 't_funds.active update'
                    }
                    if self.queue_to_db:
                        self.queue_to_db.put(data_to_db)
            if self.wait_refunding_for_start or self.tp_order_hold or self.grid_hold:
                self.get_buffered_funds()
            if self.tp_error:
                self.tp_error = False
                self.place_profit_order(after_error=True)
            if self.reverse_hold:
                if self.start_reverse_time:
                    if self.get_time() - self.start_reverse_time > 2 * SHIFT_GRID_DELAY:
                        last_price = self.get_buffered_ticker().last_price
                        if self.cycle_buy:
                            price_diff = 100 * (self.reverse_price - last_price) / self.reverse_price
                        else:
                            price_diff = 100 * (last_price - self.reverse_price) / self.reverse_price
                        if price_diff > ADX_PRICE_THRESHOLD:
                            # Reverse
                            self.cycle_buy = not self.cycle_buy
                            self.command = 'stop' if REVERSE_STOP else None
                            self.reverse = True
                            self.reverse_hold = False
                            self.sum_amount_first = self.tp_part_amount_first
                            self.sum_amount_second = self.tp_part_amount_second
                            self.tp_part_amount_first = O_DEC
                            self.tp_part_amount_second = O_DEC
                            self.message_log('Release Hold reverse cycle', color=Style.B_WHITE)
                            self.start()
                else:
                    self.start_reverse_time = self.get_time()
            # endregion
        if MODE in ('T', 'TC'):
            return {'command': json.dumps(self.command),
                    'cycle_buy': json.dumps(self.cycle_buy),
                    'cycle_buy_count': json.dumps(self.cycle_buy_count),
                    'cycle_sell_count': json.dumps(self.cycle_sell_count),
                    'cycle_time': json.dumps(self.cycle_time, default=str),
                    'cycle_time_reverse': json.dumps(self.cycle_time_reverse, default=str),
                    'deposit_first': json.dumps(self.deposit_first),
                    'deposit_second': json.dumps(self.deposit_second),
                    'last_shift_time': json.dumps(self.last_shift_time),
                    'martin': json.dumps(self.martin),
                    'order_q': json.dumps(self.order_q),
                    'orders': json.dumps(self.orders_grid.get()),
                    'orders_hold': json.dumps(self.orders_hold.get()),
                    'orders_save': json.dumps(self.orders_save.get()),
                    'over_price': json.dumps(self.over_price),
                    'part_amount': json.dumps(str(self.part_amount)),
                    'initial_first': json.dumps(self.initial_first),
                    'initial_second': json.dumps(self.initial_second),
                    'initial_reverse_first': json.dumps(self.initial_reverse_first),
                    'initial_reverse_second': json.dumps(self.initial_reverse_second),
                    'profit_first': json.dumps(self.profit_first),
                    'profit_second': json.dumps(self.profit_second),
                    'reverse': json.dumps(self.reverse),
                    'reverse_hold': json.dumps(self.reverse_hold),
                    'reverse_init_amount': json.dumps(self.reverse_init_amount),
                    'reverse_price': json.dumps(self.reverse_price),
                    'reverse_target_amount': json.dumps(self.reverse_target_amount),
                    'shift_grid_threshold': json.dumps(self.shift_grid_threshold),
                    'status_time': json.dumps(self.status_time),
                    'sum_amount_first': json.dumps(self.sum_amount_first),
                    'sum_amount_second': json.dumps(self.sum_amount_second),
                    'sum_profit_first': json.dumps(self.sum_profit_first),
                    'sum_profit_second': json.dumps(self.sum_profit_second),
                    'tp_amount': json.dumps(self.tp_amount),
                    'tp_order_id': json.dumps(self.tp_order_id),
                    'tp_part_amount_first': json.dumps(self.tp_part_amount_first),
                    'tp_part_amount_second': json.dumps(self.tp_part_amount_second),
                    'tp_target': json.dumps(self.tp_target),
                    'tp_order': json.dumps(str(self.tp_order)),
                    'tp_wait_id': json.dumps(self.tp_wait_id),
                    'restore_orders': json.dumps(self.restore_orders),
                    'tp_part_free': json.dumps(self.tp_part_free)}
        return {}

    def restore_strategy_state(self, strategy_state: Dict[str, str] = None, restore=True) -> None:
        if strategy_state:
            # Restore from file if lose state only
            self.message_log("restore_strategy_state from saved state:", log_level=LogLevel.DEBUG)
            self.message_log("\n".join(f"{k}\t{v}" for k, v in strategy_state.items()), log_level=LogLevel.DEBUG)
            #
            self.command = json.loads(strategy_state.get('command'))
            self.start_process()
            if self.command == 'stopped':
                self.message_log("Restore, strategy stopped. Need manual action", tlg=True)
                return
            #
            self.cycle_buy = json.loads(strategy_state.get('cycle_buy'))
            self.cycle_buy_count = json.loads(strategy_state.get('cycle_buy_count'))
            self.cycle_sell_count = json.loads(strategy_state.get('cycle_sell_count'))
            self.cycle_time = json.loads(strategy_state.get('cycle_time'))
            if self.cycle_time:
                self.cycle_time = datetime.strptime(self.cycle_time, '%Y-%m-%d %H:%M:%S.%f')
            self.cycle_time_reverse = json.loads(strategy_state.get('cycle_time_reverse'))
            if self.cycle_time_reverse:
                self.cycle_time_reverse = datetime.strptime(
                    self.cycle_time_reverse,
                    '%Y-%m-%d %H:%M:%S.%f'
                )
            self.deposit_first = f2d(json.loads(strategy_state.get('deposit_first')))
            self.deposit_second = f2d(json.loads(strategy_state.get('deposit_second')))
            self.last_shift_time = json.loads(strategy_state.get('last_shift_time')) or self.get_time()
            self.martin = f2d(json.loads(strategy_state.get('martin')))
            self.order_q = json.loads(strategy_state.get('order_q'))
            self.orders_grid.restore(json.loads(strategy_state.get('orders')))
            self.orders_hold.restore(json.loads(strategy_state.get('orders_hold')))
            self.orders_save.restore(json.loads(strategy_state.get('orders_save')))
            self.over_price = json.loads(strategy_state.get('over_price'))
            self.part_amount = eval(json.loads(strategy_state.get('part_amount')))
            self.initial_first = f2d(json.loads(strategy_state.get('initial_first')))
            self.initial_second = f2d(json.loads(strategy_state.get('initial_second')))
            self.initial_reverse_first = f2d(json.loads(strategy_state.get('initial_reverse_first')))
            self.initial_reverse_second = f2d(json.loads(strategy_state.get('initial_reverse_second')))
            self.profit_first = f2d(json.loads(strategy_state.get('profit_first')))
            self.profit_second = f2d(json.loads(strategy_state.get('profit_second')))
            self.reverse = json.loads(strategy_state.get('reverse'))
            self.reverse_hold = json.loads(strategy_state.get('reverse_hold'))
            self.reverse_init_amount = f2d(json.loads(strategy_state.get('reverse_init_amount')))
            self.reverse_price = json.loads(strategy_state.get('reverse_price'))
            if self.reverse_price:
                self.reverse_price = f2d(self.reverse_price)
            self.reverse_target_amount = f2d(json.loads(strategy_state.get('reverse_target_amount')))
            self.shift_grid_threshold = json.loads(strategy_state.get('shift_grid_threshold'))
            if self.shift_grid_threshold:
                self.shift_grid_threshold = f2d(self.shift_grid_threshold)
            self.status_time = json.loads(strategy_state.get('status_time'))
            self.sum_amount_first = f2d(json.loads(strategy_state.get('sum_amount_first')))
            self.sum_amount_second = f2d(json.loads(strategy_state.get('sum_amount_second')))
            self.sum_profit_first = f2d(json.loads(strategy_state.get('sum_profit_first')))
            self.sum_profit_second = f2d(json.loads(strategy_state.get('sum_profit_second')))
            self.tp_amount = f2d(json.loads(strategy_state.get('tp_amount')))
            self.tp_order_id = json.loads(strategy_state.get('tp_order_id'))
            self.tp_part_amount_first = f2d(json.loads(strategy_state.get('tp_part_amount_first')))
            self.tp_part_amount_second = f2d(json.loads(strategy_state.get('tp_part_amount_second')))
            self.tp_target = f2d(json.loads(strategy_state.get('tp_target')))
            self.tp_order = eval(json.loads(strategy_state.get('tp_order')))
            self.tp_order = self.tp_order[:3] + (self.get_time(),)
            self.tp_wait_id = json.loads(strategy_state.get('tp_wait_id'))
            self.restore_orders = json.loads(strategy_state.get('restore_orders', 'false'))
            self.tp_part_free = json.loads(strategy_state.get('tp_part_free', 'false'))
            self.first_run = False
            self.start_after_shift = False
        #
        if restore:
            self.avg_rate = self.get_buffered_ticker().last_price
            #
            open_orders = self.get_buffered_open_orders()
            tp_order = None
            # Separate TP order
            if self.tp_order_id:
                for i, o in enumerate(open_orders):
                    if o.id == self.tp_order_id:
                        tp_order = open_orders[i]
                        del open_orders[i]  # skipcq: PYL-E1138
                        break
            # Possible strategy states in compare with saved one
            grid_open_orders_len = len(open_orders)
            #
            if not grid_open_orders_len and self.orders_hold:
                self.message_log("Restore, no grid orders, place from hold now", tlg=True)
                self.place_grid_part()
            if not GRID_ONLY and self.shift_grid_threshold is None and not tp_order:
                self.message_log("Restore, no TP order, replace", tlg=True)
                self.place_profit_order()
            if not self.orders_grid and not self.orders_hold and not self.orders_save and not self.tp_order_id:
                self.message_log("Restore, Restart", tlg=True)
                self.start()
            #
            self.message_log("Restored, go work", tlg=True)

    def start(self, profit_f: Decimal = f2d(0), profit_s: Decimal = f2d(0)) -> None:
        self.message_log('Start')
        if self.command == 'stopped':
            self.message_log('Strategy stopped, waiting manual action')
            return
        # Cancel take profit order in all state
        self.tp_order_hold.clear()
        self.tp_hold = False
        self.tp_was_filled = ()
        self.order_q_placed = False
        self.grid_place_flag = False
        if self.tp_order_id:
            self.tp_cancel = True
            if not self.cancel_order_id:
                self.cancel_order_id = self.tp_order_id
                self.cancel_order_exp(self.tp_order_id)
            return
        if self.tp_wait_id:
            # Wait tp order and cancel in on_cancel_order_success and restart
            self.tp_cancel = True
            return
        ff, fs, _, _ = self.get_free_assets(mode='available')
        # Save initial funds and cycle statistics to .db for external analytics
        if self.first_run:
            if MODE in ('T', 'TC'):
                self.start_process()
            self.save_init_assets(ff, fs)
        if self.restart:
            # Check refunding before restart
            if self.cycle_buy:
                init_s = self.round_truncate(self.initial_reverse_second if self.reverse else self.initial_second,
                                             base=False)
                go_trade = fs >= init_s
                if go_trade:
                    if FEE_IN_PAIR and FEE_MAKER:
                        fs = self.initial_reverse_second if self.reverse else self.initial_second
                    _ff = ff
                    _fs = fs - profit_s
            else:
                init_f = self.round_truncate(self.initial_reverse_first if self.reverse else self.initial_first,
                                             base=True)
                go_trade = ff >= init_f
                if go_trade:
                    if FEE_IN_PAIR and FEE_MAKER:
                        ff = self.initial_reverse_first if self.reverse else self.initial_first
                    _ff = ff - profit_f
                    _fs = fs
            if go_trade:
                self.wait_refunding_for_start = False
                if MODE in ('T', 'TC') and not GRID_ONLY:
                    if self.cycle_buy:
                        df = O_DEC
                        ds = self.deposit_second - self.profit_second
                    else:
                        df = self.deposit_first - self.profit_first
                        ds = O_DEC
                    ct = datetime.utcnow() - self.cycle_time
                    ct = ct.total_seconds()
                    # noinspection PyUnboundLocalVariable
                    data_to_db = {
                        'ID_EXCHANGE': ID_EXCHANGE,
                        'f_currency': self.f_currency,
                        's_currency': self.s_currency,
                        'f_funds': _ff,
                        's_funds': _fs,
                        'avg_rate': self.avg_rate,
                        'cycle_buy': self.cycle_buy,
                        'f_depo': df,
                        's_depo': ds,
                        'f_profit': self.profit_first,
                        's_profit': self.profit_second,
                        'PRICE_SHIFT': PRICE_SHIFT,
                        'PROFIT': PROFIT,
                        'order_q': self.order_q,
                        'MARTIN': MARTIN,
                        'LINEAR_GRID_K': LINEAR_GRID_K,
                        'ADAPTIVE_TRADE_CONDITION': ADAPTIVE_TRADE_CONDITION,
                        'KBB': KBB,
                        'over_price': self.over_price,
                        'cycle_time': ct,
                        'destination': 't_funds'
                    }
                    if self.queue_to_db:
                        print('Send data to .db t_funds')
                        self.queue_to_db.put(data_to_db)
                self.save_init_assets(ff, fs)
                if COLLECT_ASSETS:
                    _ff, _fs = self.collect_assets()
                    ff -= _ff
                    fs -= _fs
            else:
                self.first_run = False
                self.wait_refunding_for_start = True
                self.message_log(f"Wait refunding for start, having now: first: {ff}, second: {fs}")
                return
        #
        self.avg_rate = self.get_buffered_ticker().last_price
        if GRID_ONLY:
            if USE_ALL_FUND and not self.start_after_shift:
                if self.cycle_buy:
                    self.deposit_second = fs
                    self.message_log(f'Use all available funds: {self.deposit_second} {self.s_currency}')
                else:
                    self.deposit_first = ff
                    self.message_log(f'Use all available funds: {self.deposit_first} {self.f_currency}')
                self.save_init_assets(ff, fs)
            if not self.check_min_amount(for_tp=False) and self.command is None:
                self.first_run = False
                self.grid_only_restart = True
                self.message_log("Waiting funding for convert", color=Style.B_WHITE)
                return
        if not self.first_run and not self.start_after_shift and not self.reverse and not GRID_ONLY:
            self.message_log(f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                             f"For all cycles profit:\n"
                             f"First: {self.sum_profit_first}\n"
                             f"Second: {self.sum_profit_second}\n"
                             f"Summary: {self.sum_profit_first * self.avg_rate + self.sum_profit_second:f}\n")
        if self.first_run or MODE in ('T', 'TC'):
            self.cycle_time = datetime.utcnow()
        #
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        total_used_percent = 100 * float(swap.used + memory.used) / (swap.total + memory.total)
        if total_used_percent > 85:
            self.message_log(f"For {VPS_NAME} critical memory availability, end", tlg=True)
            self.command = 'end'
        elif total_used_percent > 75:
            self.message_log(f"For {VPS_NAME} low memory availability, stop after end of cycle", tlg=True)
            self.command = 'stop'
        if self.command == 'end' or (self.command == 'stop' and
                                     (not self.reverse or (self.reverse and REVERSE_STOP))):
            self.command = 'stopped'
            self.start_collect = 1
            self.message_log('Stop, waiting manual action', tlg=True)
        else:
            self.message_log(f"Number of unreachable objects collected by GC: {gc.collect(generation=2)}")
            if self.first_run or self.restart:
                self.message_log(f"Initial first: {ff}, second: {fs}", color=Style.B_WHITE)
            self.restart = None
            # Init variable
            self.profit_first = O_DEC
            self.profit_second = O_DEC
            self.over_price = OVER_PRICE
            self.order_q = ORDER_Q
            self.grid_update_started = None
            #
            start_cycle_output = not self.start_after_shift or self.first_run
            if self.cycle_buy:
                amount = self.deposit_second
                if start_cycle_output:
                    self.message_log(f"Start Buy{' Reverse' if self.reverse else ''}"
                                     f" {'asset' if GRID_ONLY else 'cycle'} with {amount} {self.s_currency} depo\n"
                                     f"{'' if GRID_ONLY else self.get_free_assets(ff, fs, mode='free')[3]}", tlg=True)
            else:
                amount = self.deposit_first
                if start_cycle_output:
                    self.message_log(f"Start Sell{' Reverse' if self.reverse else ''}"
                                     f" {'asset' if GRID_ONLY else 'cycle'} with {amount} {self.f_currency} depo\n"
                                     f"{'' if GRID_ONLY else self.get_free_assets(ff, fs, mode='free')[3]}", tlg=True)
            #
            if self.reverse:
                self.message_log(f"For Reverse cycle target return amount: {self.reverse_target_amount}",
                                 color=Style.B_WHITE)
            self.debug_output()
            if self.first_run and MODE == 'TC':
                self.s_order_book = {int(self.get_time() * 1000): self.order_book}
            self.start_collect = True
            self.first_run = False
            self.place_grid(self.cycle_buy, amount, self.reverse_target_amount)

    def stop(self) -> None:
        self.message_log('Stop')
        self.queue_to_db.put({'stop_signal': True})
        self.queue_to_tlg.put(STOP_TLG)
        if self.connection_analytic:
            try:
                self.connection_analytic.execute("DELETE FROM t_orders\
                                                  WHERE id_exchange=:id_exchange\
                                                  AND f_currency=:f_currency\
                                                  AND s_currency=:s_currency",
                                                 {'id_exchange': ID_EXCHANGE,
                                                  'f_currency': self.f_currency,
                                                  's_currency': self.s_currency})
                self.connection_analytic.commit()
            except sqlite3.Error as err:
                self.message_log(f"DELETE from t_order: {err}")
            self.connection_analytic.close()
        self.connection_analytic = None

    def suspend(self) -> None:
        self.message_log('Suspend')
        self.queue_to_db.put({'stop_signal': True})
        self.queue_to_tlg.put(STOP_TLG)
        self.connection_analytic.commit()
        self.connection_analytic.close()
        self.connection_analytic = None

    def unsuspend(self) -> None:
        self.message_log('Unsuspend')
        self.start_process()

    def init_warning(self, _amount_first_grid: Decimal):
        if self.cycle_buy:
            depo = self.deposit_second
        else:
            depo = self.deposit_first
        if ADAPTIVE_TRADE_CONDITION:
            if self.first_run and self.order_q < 3:
                self.message_log(f"Depo amount {depo} not enough to set the grid with 3 or more orders",
                                 log_level=LogLevel.ERROR)
                raise SystemExit(1)
            _amount_first_grid = (_amount_first_grid * self.avg_rate) if self.cycle_buy else _amount_first_grid
            if _amount_first_grid > 80 * depo / 100:
                self.message_log(f"Recommended size of the first grid order {_amount_first_grid:f} too large for"
                                 f" a small deposit {self.deposit_second}", log_level=LogLevel.ERROR)
                if self.first_run:
                    raise SystemExit(1)
            if _amount_first_grid > 20 * depo / 100:
                self.message_log(f"Recommended size of the first grid order {_amount_first_grid:f} it is rather"
                                 f" big for a small deposit"
                                 f" {self.deposit_second if self.cycle_buy else self.deposit_first}",
                                 log_level=LogLevel.WARNING)
        else:
            first_order_vlm = depo * 1 * (1 - self.martin) / (1 - self.martin ** ORDER_Q)

            first_order_vlm = (first_order_vlm / self.avg_rate) if self.cycle_buy else first_order_vlm

            if first_order_vlm < _amount_first_grid:
                self.message_log(f"Depo amount {depo}{self.s_currency} not enough for {ORDER_Q} orders",
                                 color=Style.B_RED)
                if self.first_run:
                    raise SystemExit(1)

    def save_init_assets(self, ff, fs):
        if self.reverse:
            self.initial_reverse_first = ff
            self.initial_reverse_second = fs
        else:
            self.initial_first = ff
            self.initial_second = fs

    def collect_assets(self) -> ():
        ff, fs, _, _ = self.get_free_assets(mode='free')
        tcm = self.get_trading_capability_manager()
        if ff >= f2d(tcm.min_qty):
            self.message_log(f"Sending {ff} {self.f_currency} to main account", color=Style.UNDERLINE, tlg=True)
            self.transfer_to_master(self.f_currency, any2str(ff))
        else:
            ff = O_DEC
        if fs >= f2d(tcm.min_notional):
            self.message_log(f"Sending {fs} {self.s_currency} to main account", color=Style.UNDERLINE, tlg=True)
            self.transfer_to_master(self.s_currency, any2str(fs))
        else:
            fs = O_DEC
        return ff, fs

    def start_process(self):
        # Init analytic
        self.connection_analytic = (
                self.connection_analytic or
                sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
        )
        # Create processes for save to .db and send Telegram message
        self.pr_db = Thread(target=save_to_db, args=(self.queue_to_db,))
        self.pr_tlg = Thread(
            target=telegram,
            args=(
                self.queue_to_tlg,
                self.tlg_header.split('.')[0],
                TELEGRAM_URL,
                TOKEN,
                CHANNEL_ID,
                DB_FILE,
                STOP_TLG,
                INLINE_BOT,
            )
        )
        if not self.pr_db.is_alive():
            self.message_log('Start process for .db save')
            try:
                self.pr_db.start()
            except AssertionError as error:
                self.message_log(str(error), log_level=LogLevel.ERROR, color=Style.B_RED)
        if not self.pr_tlg.is_alive():
            self.message_log('Start process for Telegram')
            try:
                self.pr_tlg.start()
            except AssertionError as error:
                self.message_log(str(error), log_level=LogLevel.ERROR, color=Style.B_RED)

    def cancel_order_exp(self, order_id: int, cancel_all=False) -> None:
        self.cancel_order(order_id, cancel_all=cancel_all)

    ##############################################################
    # Technical analysis
    ##############################################################

    def atr(self, interval: int = 14):
        """
        Average True Range
        :param interval:
        :return:
        """
        high = []
        low = []
        close = []
        tr_arr = []
        candle = self.get_buffered_recent_candles(candle_size_in_minutes=15,
                                                  number_of_candles=interval + 1,
                                                  include_current_building_candle=True)
        for i in candle:
            high.append(i.high)
            low.append(i.low)
            close.append(i.close)
        n = 1
        while n <= len(high) - 1:
            i = max(high[n] - low[n], abs(high[n] - close[n - 1]), abs(low[n] - close[n - 1]))
            if i:
                tr_arr.append(i)
            n += 1
        # noinspection PyTypeChecker
        return f2d(statistics.geometric_mean(tr_arr))

    def adx(self, adx_candle_size_in_minutes: int, adx_number_of_candles: int, adx_period: int) -> Dict[str, float]:
        """
        Average Directional Index
        Math from https://blog.quantinsti.com/adx-indicator-python/
        Test data
        high = [90, 95, 105, 120, 140, 165, 195, 230, 270, 315, 365]
        low = [82, 85, 93, 106, 124, 147, 175, 208, 246, 289, 337]
        close = [87, 87, 97, 114, 133, 157, 186, 223, 264, 311, 350]
        ##############################################################
        """
        high = []
        low = []
        close = []
        candle = self.get_buffered_recent_candles(candle_size_in_minutes=adx_candle_size_in_minutes,
                                                  number_of_candles=adx_number_of_candles,
                                                  include_current_building_candle=True)
        for i in candle:
            high.append(i.high)
            low.append(i.low)
            close.append(i.close)
        dm_pos = []
        dm_neg = []
        tr_arr = []
        dm_pos_smooth = []
        dm_neg_smooth = []
        tr_smooth = []
        di_pos = []
        di_neg = []
        dx = []
        n = 1
        n_max = len(high) - 1
        while n <= n_max:
            m_pos = high[n] - high[n - 1]
            m_neg = low[n - 1] - low[n]
            _m_pos = 0
            _m_neg = 0
            if m_pos and m_pos > m_neg:
                _m_pos = m_pos
            if m_neg and m_neg > m_pos:
                _m_neg = m_neg
            dm_pos.append(_m_pos)
            dm_neg.append(_m_neg)
            tr = max(high[n], close[n - 1]) - min(low[n], close[n - 1])
            tr_arr.append(tr)
            if n == adx_period:
                dm_pos_smooth.append(sum(dm_pos))
                dm_neg_smooth.append(sum(dm_neg))
                tr_smooth.append(sum(tr_arr))
            if n > adx_period:
                dm_pos_smooth.append((dm_pos_smooth[-1] - dm_pos_smooth[-1] / adx_period) + _m_pos)
                dm_neg_smooth.append((dm_neg_smooth[-1] - dm_neg_smooth[-1] / adx_period) + _m_neg)
                tr_smooth.append((tr_smooth[-1] - tr_smooth[-1] / adx_period) + tr)
            if n >= adx_period:
                # Calculate +DI, -DI and DX
                di_pos.append(100 * dm_pos_smooth[-1] / tr_smooth[-1])
                di_neg.append(100 * dm_neg_smooth[-1] / tr_smooth[-1])
                dx.append(100 * abs(di_pos[-1] - di_neg[-1]) / abs(di_pos[-1] + di_neg[-1]))
            n += 1
        _adx = statistics.mean(dx[len(dx) - adx_period::])
        return {'adx': _adx, '+DI': di_pos[-1], '-DI': di_neg[-1]}

    def bollinger_band(self, candle_size_in_minutes: int, number_of_candles: int) -> Dict[str, Decimal]:
        # Bottom BB as sma-kb*stdev
        # Top BB as sma+kt*stdev
        # For Buy cycle over_price as 100*(Ticker.last_price - bbb) / Ticker.last_price
        # For Sale cycle over_price as 100*(tbb - Ticker.last_price) / Ticker.last_price
        candle_close = []
        candle = self.get_buffered_recent_candles(candle_size_in_minutes=candle_size_in_minutes,
                                                  number_of_candles=number_of_candles,
                                                  include_current_building_candle=True)
        for i in candle:
            candle_close.append(i.close)
        # print(f"bollinger_band.candle_close: {candle_close}")
        sma = statistics.mean(candle_close)
        st_dev = statistics.stdev(candle_close)
        # print('sma={}, st_dev={}'.format(sma, st_dev))
        tbb = sma + KBB * st_dev
        bbb = sma - KBB * st_dev
        min_price = self.get_trading_capability_manager().get_minimal_price_change()
        bbb = max(bbb, min_price)
        # self.message_log(f"bollinger_band: tbb={tbb:f}, bbb={bbb:f}", log_level=LogLevel.DEBUG)
        return {'tbb': f2d(tbb), 'bbb': f2d(bbb)}

    ##############################################################
    # supplementary methods
    ##############################################################
    def get_sum_profit(self):
        return self.round_truncate(self.sum_profit_first * self.avg_rate + self.sum_profit_second, base=False)

    def debug_output(self):
        self.message_log(f"\n"
                         f"! =======================================\n"
                         f"! debug output: ver: {self.client.srv_version}: {HEAD_VERSION}+{__version__}+{msb_ver}\n"
                         f"! sum_amount_first: {self.sum_amount_first}, sum_amount_second: {self.sum_amount_second}\n"
                         f"! part_amount: {self.part_amount}\n"
                         f"! initial_first: {self.initial_first}, initial_second: {self.initial_second}\n"
                         f"! initial_reverse_first: {self.initial_reverse_first},"
                         f" initial_reverse_second: {self.initial_reverse_second}\n"
                         f"! reverse_init_amount: {self.reverse_init_amount}\n"
                         f"! reverse_target_amount: {self.reverse_target_amount}\n"
                         f"! tp_order: {self.tp_order}\n"
                         f"! tp_part_amount_first: {self.tp_part_amount_first},"
                         f" tp_part_amount_second: {self.tp_part_amount_second}\n"
                         f"! profit_first: {self.profit_first}, profit_second: {self.profit_second}\n"
                         f"! part_profit_first: {self.part_profit_first},"
                         f" part_profit_second: {self.part_profit_second}\n"
                         f"! deposit_first: {self.deposit_first}, deposit_second: {self.deposit_second}\n"
                         f"! command: {self.command}\n"
                         f"! reverse: {self.reverse}\n"
                         f"! Profit: {self.get_sum_profit()}\n"
                         f"! ======================================",
                         log_level=LogLevel.DEBUG)

    def get_free_assets(self, ff: Decimal = None, fs: Decimal = None, mode: str = 'total', backtest=False) -> ():
        """
        Get free asset for current trade pair
        :param fs:
        :param ff:
        :param mode: 'total', 'available', 'reserved', 'free'
        :param backtest: bool
        :return: (ff, fs, ft, free_asset: str)
        """
        if ff is None or fs is None:
            funds = self.get_buffered_funds()
            _ff = funds.get(self.f_currency, O_DEC)
            _fs = funds.get(self.s_currency, O_DEC)
            ff = O_DEC
            fs = O_DEC
            if _ff and _fs:
                if mode == 'total':
                    ff = _ff.total_for_currency
                    fs = _fs.total_for_currency
                elif mode in ('available', 'free'):
                    ff = _ff.available
                    fs = _fs.available
                elif mode == 'reserved':
                    ff = _ff.reserved
                    fs = _fs.reserved
        #
        if mode == 'free':
            if self.cycle_buy:
                if backtest:
                    ff = self.initial_reverse_first if self.reverse else self.initial_first
                fs = (self.initial_reverse_second if self.reverse else self.initial_second) - self.deposit_second
            else:
                ff = (self.initial_reverse_first if self.reverse else self.initial_first) - self.deposit_first
                if backtest:
                    fs = self.initial_reverse_second if self.reverse else self.initial_second
        ff = self.round_truncate(ff, base=True)
        fs = self.round_truncate(fs, base=False)
        ft = ff * self.avg_rate + fs
        assets = f"{mode.capitalize()}: First: {ff}, Second: {fs}"
        return ff, fs, ft, assets

    def round_truncate(self, _x: Decimal, base: bool = None, fee=False, _rounding=ROUND_FLOOR) -> Decimal:
        if fee:
            round_pattern = "1.01234567"
        else:
            round_pattern = self.round_base if base else self.round_quote
        return _x.quantize(Decimal(round_pattern), rounding=_rounding)

    def round_fee(self, fee, amount, base):
        return self.round_truncate(fee * amount / 100, base=base, fee=True, _rounding=ROUND_CEILING)

    def depo_unused(self):
        if self.cycle_buy:
            _depo = self.deposit_second - self.sum_amount_second
        else:
            _depo = self.deposit_first - self.sum_amount_first
        return _depo

    ##############################################################
    # strategy function
    ##############################################################
    def place_grid(self,
                   buy_side: bool,
                   depo: Decimal,
                   reverse_target_amount: Decimal,
                   allow_grid_shift: bool = True,
                   additional_grid: bool = False,
                   grid_update: bool = False) -> None:
        self.message_log(f"place_grid: buy_side: {buy_side}, depo: {depo},"
                         f" reverse_target_amount: {reverse_target_amount},"
                         f" allow_grid_shift: {allow_grid_shift},"
                         f" additional_grid: {additional_grid},"
                         f" grid_update: {grid_update}", log_level=LogLevel.DEBUG)
        self.grid_hold.clear()
        self.last_shift_time = None
        self.wait_wss_refresh = {}
        funds = self.get_buffered_funds()
        if buy_side:
            currency = self.s_currency
            fund = funds.get(currency, O_DEC)
            fund = fund.available if fund else O_DEC
        else:
            currency = self.f_currency
            fund = funds.get(currency, O_DEC)
            fund = fund.available if fund else O_DEC
        if depo <= fund:
            tcm = self.get_trading_capability_manager()
            last_executed_grid_price = self.avg_rate if grid_update else O_DEC
            if buy_side:
                _price = last_executed_grid_price or self.get_buffered_order_book().bids[0].price
                base_price = _price - PRICE_SHIFT * _price / 100
                amount_min = tcm.get_min_buy_amount(base_price)
            else:
                _price = last_executed_grid_price or self.get_buffered_order_book().asks[0].price
                base_price = _price + PRICE_SHIFT * _price / 100
                amount_min = tcm.get_min_sell_amount(base_price)
            min_delta = tcm.get_minimal_price_change()
            base_price = tcm.round_price(base_price, ROUND_HALF_EVEN)
            # Adjust min_amount order quantity per fee
            _f, _s = self.fee_for_grid(amount_min, amount_min * self.avg_rate, by_market=True, print_info=False)
            if _f != amount_min:
                amount_min += amount_min - _f
            elif _s != amount_min * self.avg_rate:
                amount_min += (amount_min * self.avg_rate - _s) / self.avg_rate
            amount_min = self.round_truncate(amount_min, base=True, _rounding=ROUND_CEILING)
            #
            if ADAPTIVE_TRADE_CONDITION or self.reverse or additional_grid:
                try:
                    amount_first_grid = self.set_trade_conditions(buy_side,
                                                                  depo,
                                                                  base_price,
                                                                  reverse_target_amount,
                                                                  min_delta,
                                                                  amount_min,
                                                                  additional_grid=additional_grid,
                                                                  grid_update=grid_update)
                except statistics.StatisticsError as ex:
                    self.message_log(f"Can't set trade conditions: {ex}, waiting for WSS data update",
                                     log_level=LogLevel.WARNING)
                    self.wait_wss_refresh = {
                              'buy_side': buy_side,
                              'depo': depo,
                              'allow_grid_shift': allow_grid_shift,
                              'additional_grid': additional_grid,
                              'grid_update': grid_update,
                              'timestamp': self.get_time()
                    }
                    return
                except Exception as ex:
                    self.message_log(f"Can't set trade conditions: {ex}", log_level=LogLevel.ERROR)
                    return
            else:
                self.over_price = OVER_PRICE
                self.order_q = ORDER_Q
                amount_first_grid = amount_min
            if self.order_q > 1:
                self.message_log(f"For{' Reverse' if self.reverse else ''} {'Buy' if buy_side else 'Sell'}"
                                 f" cycle set {self.order_q} orders for {float(self.over_price):.4f}% over price",
                                 tlg=False)
            else:
                self.message_log(f"For{' Reverse' if self.reverse else ''} {'Buy' if buy_side else 'Sell'}"
                                 f" cycle set {self.order_q} order{' for additional grid' if additional_grid else ''}",
                                 tlg=False)
            #
            if self.first_run:
                self.init_warning(amount_first_grid)
            #
            if self.order_q == 1:
                if self.reverse:
                    price = (depo / reverse_target_amount) if buy_side else (reverse_target_amount / depo)
                else:
                    price = base_price
                price = tcm.round_price(price, ROUND_HALF_EVEN)
                amount = self.round_truncate((depo / price) if buy_side else depo, base=True, _rounding=ROUND_FLOOR)
                orders = [(0, amount, price)]
            else:
                params = {'buy_side': buy_side,
                          'depo': depo,
                          'base_price': base_price,
                          'amount_first_grid': amount_first_grid,
                          'min_delta': min_delta,
                          'amount_min': amount_min}
                grid_calc = self.calc_grid(self.over_price, calc_avg_amount=False, **params)
                orders = grid_calc['orders']
                total_grid_amount_f = grid_calc['total_grid_amount_f']
                total_grid_amount_s = grid_calc['total_grid_amount_s']
                self.message_log(f"Total grid amount: first: {total_grid_amount_f}, second: {total_grid_amount_s}",
                                 log_level=LogLevel.DEBUG, color=Style.CYAN)
            #
            for order in orders:
                i, amount, price = order
                # create order for grid
                if i < GRID_MAX_COUNT:
                    waiting_order_id = self.place_limit_order(buy_side, amount, price)
                    self.orders_init.append_order(waiting_order_id, buy_side, amount, price)
                else:
                    self.orders_hold.append_order(i, buy_side, amount, price)
            #
            if allow_grid_shift:
                bb = None
                if GRID_ONLY:
                    try:
                        bb = self.bollinger_band(15, BB_NUMBER_OF_CANDLES)
                    except Exception as ex:
                        self.message_log(f"Can't get BollingerBand: {ex}", log_level=LogLevel.ERROR)
                    else:
                        if buy_side:
                            self.shift_grid_threshold = bb.get('tbb')
                        else:
                            self.shift_grid_threshold = bb.get('bbb')
                if not GRID_ONLY or (GRID_ONLY and bb is None):
                    if buy_side:
                        self.shift_grid_threshold = base_price + 2 * PRICE_SHIFT * base_price / 100
                    else:
                        self.shift_grid_threshold = base_price - 2 * PRICE_SHIFT * base_price / 100
                self.message_log(f"Shift grid threshold: {self.shift_grid_threshold:f}")
            #
            self.start_after_shift = False
            if self.grid_update_started:
                self.grid_place_flag = None
                self.grid_update_started = None
        else:
            self.grid_hold = {'buy_side': buy_side,
                              'depo': depo,
                              'reverse_target_amount': reverse_target_amount,
                              'allow_grid_shift': allow_grid_shift,
                              'additional_grid': additional_grid,
                              'grid_update': grid_update,
                              'timestamp': self.get_time()}
            self.message_log(f"Hold grid for {'Buy' if buy_side else 'Sell'} cycle with {depo} {currency} depo."
                             f" Available funds is {fund} {currency}", tlg=False)
        if self.tp_hold_additional:
            self.message_log("Replace take profit order after place additional grid orders", tlg=True)
            self.tp_hold = False
            self.tp_hold_additional = False
            self.place_profit_order()

    def calc_grid(self, over_price: Decimal, calc_avg_amount=True, **kwargs):
        if isinstance(over_price, np.ndarray):
            over_price = float(over_price[0])
        over_price = f2d(over_price)

        buy_side = kwargs.get('buy_side')
        depo = kwargs.get('depo')
        base_price = kwargs.get('base_price')
        amount_first_grid = kwargs.get('amount_first_grid')
        min_delta = kwargs.get('min_delta')
        amount_min = kwargs.get('amount_min')

        tcm = self.get_trading_capability_manager()
        delta_price = over_price * base_price / (100 * (self.order_q - 1))
        price_prev = base_price
        avg_amount = O_DEC
        total_grid_amount_f = O_DEC
        total_grid_amount_s = O_DEC
        depo_i = O_DEC
        rounding = ROUND_CEILING
        last_order_pass = False
        price_k = 1
        amount_last_grid = O_DEC
        orders = []

        for i in range(self.order_q):
            if LINEAR_GRID_K >= 0:
                price_k = f2d(1 - math.log(self.order_q - i, self.order_q + LINEAR_GRID_K))
            price = base_price - i * delta_price * price_k if buy_side else base_price + i * delta_price * price_k
            price = tcm.round_price(price, ROUND_HALF_EVEN)

            if buy_side and i and price_prev - price < min_delta:
                price = price_prev - min_delta
            elif not buy_side and i and price - price_prev < min_delta:
                price = price_prev + min_delta

            if buy_side:
                price = max(price, tcm.get_min_price())
            else:
                price = min(price, tcm.get_max_price())

            price_prev = price

            if i == 0:
                amount_0 = depo * self.martin ** i * (self.martin - 1) / (self.martin ** self.order_q - 1)
                amount = max(amount_0, amount_first_grid * (price if buy_side else 1))
                depo_i = depo - amount
            elif i < self.order_q - 1:
                amount = depo_i * self.martin ** i * (self.martin - 1) / (self.martin ** self.order_q - 1)
            else:
                amount = amount_last_grid
                rounding = ROUND_FLOOR

            if buy_side:
                amount /= price

            amount = self.round_truncate(amount, base=True, _rounding=rounding)
            total_grid_amount_f += amount
            total_grid_amount_s += amount * price

            if i == self.order_q - 2:
                amount_last_grid = depo - (total_grid_amount_s if buy_side else total_grid_amount_f)
                if amount_last_grid < amount_min * (price if buy_side else 1):
                    total_grid_amount_f -= amount
                    total_grid_amount_s -= amount * price
                    amount += amount_last_grid / (price if buy_side else 1)
                    amount = self.round_truncate(amount, base=True, _rounding=ROUND_FLOOR)
                    last_order_pass = True

            if buy_side:
                avg_amount += amount
            else:
                avg_amount += amount * price

            if not calc_avg_amount:
                orders.append((i, amount, price))

            if last_order_pass:
                total_grid_amount_f += amount
                total_grid_amount_s += amount * price
                break

        if calc_avg_amount:
            return float(avg_amount)

        return {
            'total_grid_amount_f': total_grid_amount_f,
            'total_grid_amount_s': total_grid_amount_s,
            'orders': orders
        }

    def grid_update(self):
        do_it = False
        depo_remaining = self.depo_unused() / (self.deposit_second if self.cycle_buy else self.deposit_first)

        if self.reverse and depo_remaining >= f2d(0.65):
            if self.get_time() - self.ts_grid_update > GRID_UPDATE_INTERVAL:
                do_it = True
        elif not self.reverse and depo_remaining >= f2d(0.35):
            try:
                bb = self.bollinger_band(BB_CANDLE_SIZE_IN_MINUTES, BB_NUMBER_OF_CANDLES)
            except Exception as ex:
                self.message_log(f"Can't get BB in grid update: {ex}", log_level=LogLevel.INFO)
            else:
                if self.heartbeat_counter % 150 == 0:
                    frequency = 'low'
                elif self.heartbeat_counter % 30 == 0:
                    frequency = 'mid'
                else:
                    frequency = 'hi'
                #
                last_price = self.orders_hold.get_last()[3] if self.orders_hold else self.orders_grid.get_last()[3]
                predicted_price = bb.get('bbb') if self.cycle_buy else bb.get('tbb')
                if self.cycle_buy:
                    delta = 100 * (last_price - predicted_price) / last_price
                else:
                    delta = 100 * (predicted_price - last_price) / last_price
                #
                if delta > 0:
                    if frequency == 'hi':
                        do_it = delta > f2d(0.5)
                    elif frequency == 'mid':
                        do_it = delta > f2d(0.25)
                    elif frequency == 'low':
                        do_it = delta > f2d(0.12)
                elif delta < 0 and frequency == 'low':
                    do_it = -1 * delta > 3
        if do_it:
            if self.reverse:
                self.message_log("Update grid in Reverse cycle", color=Style.B_WHITE)
            else:
                # noinspection PyUnboundLocalVariable
                self.message_log(f"Update grid orders, frequency: {frequency},"
                                 f" BB limit difference: {float(delta):.2f}%", color=Style.B_WHITE)
            self.grid_update_started = True
            self.cancel_grid()

    def place_profit_order(self, by_market=False, after_error=False) -> None:
        if not GRID_ONLY and self.check_min_amount():
            self.tp_order_hold.clear()
            if self.tp_wait_id or self.cancel_order_id or self.tp_was_filled:
                # Waiting confirm or cancel old or processing ending and replace it
                self.tp_hold = True
                self.message_log('Waiting finished TP order for replace', color=Style.B_WHITE)
            elif self.tp_order_id:
                # Cancel take profit order, place new
                self.tp_hold = True
                self.cancel_order_id = self.tp_order_id
                self.cancel_order_exp(self.tp_order_id)
                self.message_log('Hold take profit order, replace existing', color=Style.B_WHITE)
            else:
                buy_side = not self.cycle_buy
                # Calculate take profit order
                tp = self.calc_profit_order(buy_side, by_market=by_market)
                price = tp.get('price')
                amount = tp.get('amount')
                profit = tp.get('profit')
                target = tp.get('target')
                # Check funds available
                funds = self.get_buffered_funds()
                if buy_side:
                    fund = funds.get(self.s_currency, O_DEC)
                    fund = fund.available if fund else O_DEC
                else:
                    fund = funds.get(self.f_currency, O_DEC)
                    fund = fund.available if fund else O_DEC
                if buy_side and amount * price > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side,
                                          'amount': amount * price,
                                          'by_market': by_market,
                                          'timestamp': self.get_time()}
                    self.message_log(f"Hold take profit order for Buy {amount} {self.f_currency} by {price},"
                                     f" wait {amount * price} {self.s_currency}, exist: {fund}")
                elif not buy_side and amount > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side,
                                          'amount': amount,
                                          'by_market': by_market,
                                          'timestamp': self.get_time()}
                    self.message_log(f"Hold take profit order for Sell {amount} {self.f_currency}"
                                     f" by {price}, exist {fund}")
                else:
                    # Create take profit order
                    self.message_log(f"Create {'Buy' if buy_side else 'Sell'} take profit order,"
                                     f" vlm: {amount}, price: {price}, profit: {profit}%")
                    self.tp_target = target
                    self.tp_order = (buy_side, amount, price, self.get_time())
                    check = after_error or (len(self.orders_grid) + len(self.orders_hold)) > 2
                    self.tp_wait_id = self.place_limit_order_check(buy_side, amount, price, check=check)
        elif self.tp_order_id and self.tp_cancel:
            self.cancel_order_id = self.tp_order_id
            self.cancel_order_exp(self.tp_order_id)
            self.message_log('Try cancel TPO, then Start', color=Style.B_WHITE)

    def set_trade_conditions(self,
                             buy_side: bool,
                             depo: Decimal,
                             base_price: Decimal,
                             reverse_target_amount: Decimal,
                             delta_min: Decimal,
                             amount_min: Decimal,
                             additional_grid: bool = False,
                             grid_update: bool = False) -> Decimal:
        tcm = self.get_trading_capability_manager()
        step_size = tcm.get_minimal_amount_change()
        self.message_log(f"set_trade_conditions: buy_side: {buy_side}, depo: {float(depo):f},"
                         f" base_price: {base_price}, reverse_target_amount: {reverse_target_amount},"
                         f" amount_min: {amount_min}, step_size: {step_size}, delta_min: {delta_min}",
                         LogLevel.DEBUG)
        depo_c = (depo / base_price) if buy_side else depo
        if not additional_grid and not grid_update and not GRID_ONLY and 0 < PROFIT_MAX < 100:
            try:
                profit_max = min(PROFIT_MAX, max(PROFIT, 100 * self.atr() / self.get_buffered_ticker().last_price))
            except statistics.StatisticsError as ex:
                self.message_log(f"Can't get ATR value: {ex}, use default PROFIT value", LogLevel.WARNING)
                profit_max = PROFIT
            self.message_log(f"Profit max for first order volume is set {float(profit_max):f}%", LogLevel.DEBUG)
            k_m = 1 - profit_max / 100
            amount_first_grid = max(amount_min, (step_size * base_price / ((1 / k_m) - 1)) / base_price)
            amount_first_grid = self.round_truncate(amount_first_grid, base=True, _rounding=ROUND_CEILING)
            if amount_first_grid >= depo_c:
                raise UserWarning(f"Amount first grid order: {amount_first_grid} is greater than depo:"
                                  f" {float(depo_c):f}. Increase depo amount.")
        else:
            amount_first_grid = amount_min
        if self.reverse:
            over_price = self.calc_over_price(buy_side,
                                              depo,
                                              base_price,
                                              reverse_target_amount,
                                              delta_min,
                                              amount_first_grid,
                                              amount_min)
        else:
            bb = self.bollinger_band(BB_CANDLE_SIZE_IN_MINUTES, BB_NUMBER_OF_CANDLES)
            if buy_side:
                bbb = bb.get('bbb')
                over_price = 100 * (base_price - bbb) / base_price
            else:
                tbb = bb.get('tbb')
                over_price = 100 * (tbb - base_price) / base_price
        self.over_price = max(over_price, OVER_PRICE)
        # Adapt grid orders quantity for current over price
        order_q = int(self.over_price * ORDER_Q / OVER_PRICE)
        amnt_2 = amount_min * self.martin
        q_max = int(math.log(1 + (depo_c - amount_first_grid) * self.martin * (self.martin - 1) / amnt_2, self.martin))
        self.message_log(f"set_trade_conditions: depo: {float(depo):f}, order_q: {order_q},"
                         f" amount_first_grid: {amount_first_grid:f}, amount_2: {amnt_2:f},"
                         f" q_max: {q_max}, coarse overprice: {float(self.over_price):f}", LogLevel.DEBUG)
        while q_max > ORDER_Q or (GRID_ONLY and q_max > 1):
            delta_price = self.over_price * base_price / (100 * (q_max - 1))
            if LINEAR_GRID_K >= 0:
                price_k = f2d(1 - math.log(q_max - 1, q_max + LINEAR_GRID_K))
            else:
                price_k = 1
            delta = delta_price * price_k
            if delta > delta_min:
                break
            q_max -= 1
        #
        self.order_q = max(q_max if order_q > q_max else order_q, 1)
        # Correction over_price after change orders count
        if self.reverse and self.order_q > 1:
            over_price = self.calc_over_price(buy_side,
                                              depo,
                                              base_price,
                                              reverse_target_amount,
                                              delta_min,
                                              amount_first_grid,
                                              amount_min,
                                              over_price)
            self.over_price = max(over_price, OVER_PRICE)
        return amount_first_grid

    def set_profit(self, amount: Decimal, by_market: bool) -> Decimal:
        fee = FEE_TAKER if by_market else FEE_MAKER
        fee = fee if FEE_IN_PAIR else fee + FEE_MAKER
        tbb = None
        bbb = None
        n = len(self.orders_grid) + len(self.orders_init) + len(self.orders_hold) + len(self.orders_save)
        if PROFIT_MAX and (n > 1 or self.reverse):
            try:
                bb = self.bollinger_band(15, 20)
            except statistics.StatisticsError:
                self.message_log("Set profit Exception, can't calculate BollingerBand, set profit by default",
                                 log_level=LogLevel.WARNING)
            else:
                tbb = bb.get('tbb', O_DEC)
                bbb = bb.get('bbb', O_DEC)
        if tbb and bbb:
            if self.cycle_buy:
                profit = 100 * (tbb * amount - self.tp_amount) / self.tp_amount
            else:
                profit = 100 * (amount / bbb - self.tp_amount) / self.tp_amount
            profit = min(max(profit, PROFIT + fee), PROFIT_MAX)
        else:
            profit = PROFIT + fee
        return profit.quantize(Decimal("1.0123"), rounding=ROUND_CEILING)

    def calc_profit_order(self, buy_side: bool, by_market: bool = False) -> Dict[str, Decimal]:
        """
        Calculation based on amount value
        :param buy_side: for take profit order, inverse to current cycle
        :param by_market:
        :return:
        """
        self.message_log(f"calc_profit_order: buy_side: {buy_side}, by_market: {by_market}", LogLevel.DEBUG)
        tcm = self.get_trading_capability_manager()
        step_size_f = tcm.get_minimal_amount_change()
        if buy_side:
            # Calculate target amount for first
            self.tp_amount = self.sum_amount_first
            profit = self.set_profit(self.sum_amount_second, by_market)
            target_amount_first = self.sum_amount_first + profit * self.sum_amount_first / 100
            if target_amount_first - self.tp_amount < step_size_f:
                target_amount_first = self.tp_amount + step_size_f
            target_amount_first = self.round_truncate(target_amount_first, base=True, _rounding=ROUND_FLOOR)
            amount = target = target_amount_first
            # Calculate depo amount in second
            amount_s = self.round_truncate(self.sum_amount_second, base=False, _rounding=ROUND_FLOOR)
            price = tcm.round_price(amount_s / target_amount_first, ROUND_FLOOR)
        else:
            step_size_s = self.round_truncate((step_size_f * self.avg_rate), base=False, _rounding=ROUND_CEILING)
            # Calculate target amount for second
            self.tp_amount = self.sum_amount_second
            profit = self.set_profit(self.sum_amount_first, by_market)
            target_amount_second = self.sum_amount_second + profit * self.sum_amount_second / 100
            if target_amount_second - self.tp_amount < step_size_s:
                target_amount_second = self.tp_amount + step_size_s
            target_amount_second = self.round_truncate(target_amount_second, base=False, _rounding=ROUND_CEILING)
            # Calculate depo amount in first
            amount = self.round_truncate(self.sum_amount_first, base=True, _rounding=ROUND_FLOOR)
            price = tcm.round_price(target_amount_second / amount, ROUND_CEILING)
            target = amount * price
        # Calc real margin for TP
        profit = (100 * (target - self.tp_amount) / self.tp_amount).quantize(Decimal("1.0123"), rounding=ROUND_FLOOR)
        self.message_log(f"calc_profit_order: Initial depo for TP: {self.tp_amount},"
                         f" target {'first' if buy_side else 'second'}: {target}",
                         log_level=LogLevel.DEBUG)
        return {'price': price, 'amount': amount, 'profit': profit, 'target': target}

    def calc_over_price(self,
                        buy_side: bool,
                        depo: Decimal,
                        base_price: Decimal,
                        reverse_target_amount: Decimal,
                        min_delta: Decimal,
                        amount_first_grid: Decimal,
                        amount_min: Decimal,
                        over_price_previous: Decimal = None) -> Decimal:
        """
        Calculate over price for depo refund after Reverse cycle
        :param buy_side:
        :param depo:
        :param base_price:
        :param reverse_target_amount:
        :param min_delta:
        :param amount_first_grid:
        :param amount_min:
        :param over_price_previous:
        :return: Decimal calculated over price
        """
        self.message_log(f"calc_over_price: buy_side: {buy_side}, depo: {depo:.6f}, base_price: {base_price:f},"
                         f" reverse_target_amount: {reverse_target_amount}, order_q: {self.order_q},"
                         f" amount_first_grid: {amount_first_grid}",
                         log_level=LogLevel.DEBUG)
        if buy_side:
            over_price_coarse = 100 * (base_price - (depo / reverse_target_amount)) / base_price
            max_err = self.round_truncate(f2d(0.00000001), base=True, _rounding=ROUND_CEILING)
        else:
            over_price_coarse = 100 * ((reverse_target_amount / depo) - base_price) / base_price
            max_err = self.round_truncate(f2d(0.00000001), base=False, _rounding=ROUND_CEILING)
        max_err *= 10
        self.message_log(f"over_price coarse: {float(over_price_coarse):.6f}, max_err: {max_err}",
                         log_level=LogLevel.DEBUG)
        if self.order_q > 1 and over_price_coarse > 0:
            # Fine calculate over_price for target return amount
            params = {'buy_side': buy_side,
                      'depo': depo,
                      'base_price': base_price,
                      'amount_first_grid': amount_first_grid,
                      'min_delta': min_delta,
                      'amount_min': amount_min}

            over_price, msg = solve(self.calc_grid, reverse_target_amount, over_price_coarse, **params)

            if over_price == 0:
                self.message_log(f"{msg}, use previous or over_price_coarse * 2", log_level=LogLevel.ERROR)
                over_price = over_price_previous or 2 * over_price_coarse
            else:
                self.message_log(msg)
        else:
            over_price = over_price_coarse
        return over_price

    def fee_for_grid(self,
                     amount_first: Decimal,
                     amount_second: Decimal,
                     by_market: bool = False,
                     print_info: bool = True) -> (Decimal, Decimal):
        """
        Calculate trade amount with Fee for grid order for both currency
        """
        message = str()
        if FEE_IN_PAIR:
            fee = FEE_TAKER if by_market else FEE_MAKER
            if FEE_BNB_IN_PAIR:
                if self.cycle_buy:
                    amount_first -= self.round_fee(fee, amount_first, base=True)
                    message = f"For grid order First - fee: {float(amount_first):f}"
                else:
                    amount_first += self.round_fee(fee, amount_first, base=True)
                    message = f"For grid order First + fee: {float(amount_first):f}"
            else:
                if self.cycle_buy:
                    if FEE_SECOND:
                        amount_second += self.round_fee(fee, amount_second, base=False)
                        message = f"For grid order Second + fee: {float(amount_second):f}"
                    else:
                        amount_first -= self.round_fee(fee, amount_first, base=True)
                        message = f"For grid order First - fee: {float(amount_first):f}"
                else:
                    amount_second -= self.round_fee(fee, amount_second, base=False)
                    message = f"For grid order Second - fee: {float(amount_second):f}"
        if print_info and message:
            self.message_log(message, log_level=LogLevel.DEBUG)
        return self.round_truncate(amount_first, fee=True), self.round_truncate(amount_second, fee=True)

    def fee_for_tp(self,
                   amount_first: Decimal,
                   amount_second: Decimal,
                   by_market=False,
                   log_output=True) -> (Decimal, Decimal):
        """
        Calculate trade amount with Fee for take profit order for both currency
        """
        if FEE_IN_PAIR:
            fee = FEE_TAKER if by_market else FEE_MAKER
            if FEE_BNB_IN_PAIR:
                if self.cycle_buy:
                    amount_first += self.round_fee(fee, amount_first, base=True)
                    log_text = f"Take profit order First + fee: {amount_first}"
                else:
                    amount_first -= self.round_fee(fee, amount_first, base=True)
                    log_text = f"Take profit order First - fee: {amount_first}"
            else:
                if self.cycle_buy:
                    amount_second -= self.round_fee(fee, amount_second, base=False)
                    log_text = f"Take profit order Second - fee: {amount_second}"
                else:
                    if FEE_SECOND:
                        amount_second += self.round_fee(fee, amount_second, base=False)
                        log_text = f"Take profit order Second + fee: {amount_second}"
                    else:
                        amount_first -= self.round_fee(fee, amount_first, base=True)
                        log_text = f"Take profit order First - fee: {amount_first}"
            if log_output:
                self.message_log(log_text, log_level=LogLevel.DEBUG)
        return self.round_truncate(amount_first, fee=True), self.round_truncate(amount_second, fee=True)

    def after_filled_tp(self, one_else_grid: bool = False):
        """
        After filling take profit order calculate profit, deposit and restart or place additional TP
        """
        # noinspection PyTupleAssignmentBalance
        amount_first, amount_second, by_market = self.tp_was_filled  # skipcq: PYL-W0632
        self.message_log(f"after_filled_tp: amount_first: {float(amount_first):f},"
                         f" amount_second: {float(amount_second):f},"
                         f" by_market: {by_market}, tp_amount: {self.tp_amount}, tp_target: {self.tp_target}"
                         f" one_else_grid: {one_else_grid}", log_level=LogLevel.DEBUG)
        self.debug_output()
        amount_first_fee, amount_second_fee = self.fee_for_tp(amount_first, amount_second, by_market)
        # Calculate cycle and total profit, refresh depo
        profit_first = profit_second = O_DEC
        if self.cycle_buy:
            profit_second = self.round_truncate(amount_second_fee - self.tp_amount, base=False)
            profit_reverse = profit_second if self.reverse and self.cycle_buy_count % 2 == 0 else O_DEC
            profit_second -= profit_reverse
            self.profit_second += profit_second
            self.part_profit_second = O_DEC
            self.message_log(f"Cycle profit second {self.profit_second} + {profit_reverse}")
        else:
            profit_first = self.round_truncate(amount_first_fee - self.tp_amount, base=True)
            profit_reverse = profit_first if self.reverse and self.cycle_sell_count % 2 == 0 else O_DEC
            profit_first -= profit_reverse
            self.profit_first += profit_first
            self.part_profit_first = O_DEC
            self.message_log(f"Cycle profit first {self.profit_first} + {profit_reverse}")
        transfer_sum_amount_first = transfer_sum_amount_second = O_DEC
        if one_else_grid:
            self.message_log("Some grid orders was execute after TP was filled", tlg=True)
            self.tp_was_filled = ()
            if self.convert_tp(amount_first_fee - profit_first, amount_second_fee - profit_second):
                return
            self.message_log("Transfer filled TP amount to the next cycle", tlg=True)
            transfer_sum_amount_first = self.sum_amount_first
            transfer_sum_amount_second = self.sum_amount_second
        if self.cycle_buy:
            self.deposit_second += self.profit_second - transfer_sum_amount_second
            if self.reverse:
                self.sum_profit_second += profit_reverse
                profit_f = transfer_sum_amount_first
                profit_s = self.profit_second + profit_reverse - transfer_sum_amount_second
                self.initial_reverse_first += profit_f
                self.initial_reverse_second += profit_s
            else:
                # Take full profit only for non-reverse cycle
                self.sum_profit_second += self.profit_second
                profit_f = transfer_sum_amount_first
                profit_s = self.profit_second - transfer_sum_amount_second
                self.initial_first += profit_f
                self.initial_second += profit_s
            self.message_log(f"after_filled_tp: new initial_funding:"
                             f" {self.initial_reverse_second if self.reverse else self.initial_second}",
                             log_level=LogLevel.INFO)
            self.cycle_buy_count += 1
        else:
            self.deposit_first += self.profit_first - transfer_sum_amount_first
            if self.reverse:
                self.sum_profit_first += profit_reverse
                profit_f = self.profit_first + profit_reverse - transfer_sum_amount_first
                profit_s = transfer_sum_amount_second
                self.initial_reverse_first += profit_f
                self.initial_reverse_second += profit_s
            else:
                # Take full account profit only for non-reverse cycle
                self.sum_profit_first += self.profit_first
                profit_f = self.profit_first - transfer_sum_amount_first
                profit_s = transfer_sum_amount_second
                self.initial_first += profit_f
                self.initial_second += profit_s
            self.message_log(f"after_filled_tp: new initial_funding:"
                             f" {self.initial_reverse_first if self.reverse else self.initial_first}",
                             log_level=LogLevel.INFO)
            self.cycle_sell_count += 1
        if (not self.cycle_buy and self.profit_first < 0) or (self.cycle_buy and self.profit_second < 0):
            self.message_log("Strategy have a negative cycle result, STOP", log_level=LogLevel.CRITICAL)
            self.command = 'end'
            self.tp_was_filled = ()
            self.cancel_grid(cancel_all=True)
        else:
            self.message_log("Restart after filling take profit order", tlg=False)
        self.part_profit_first = self.part_profit_second = O_DEC
        self.restart = True
        self.sum_amount_first = transfer_sum_amount_first
        self.sum_amount_second = transfer_sum_amount_second
        self.part_amount.clear()
        self.tp_part_amount_first = self.tp_part_amount_second = O_DEC
        self.debug_output()
        self.start(profit_f, profit_s)

    def reverse_after_grid_ending(self):
        self.message_log("Reverse after grid ending:", log_level=LogLevel.DEBUG)
        self.debug_output()
        profit_f = profit_s = O_DEC
        if self.reverse:
            self.message_log('End reverse cycle', tlg=True)
            self.reverse = False
            self.restart = True
            # Calculate profit and time for Reverse cycle
            self.cycle_time = self.cycle_time_reverse or datetime.utcnow()
            if self.cycle_buy:
                self.profit_first += self.round_truncate(self.sum_amount_first - self.reverse_init_amount +
                                                         self.tp_part_amount_first, base=True)
                profit_f = self.round_truncate(self.profit_first - self.tp_part_amount_first, base=True)
                self.deposit_first += profit_f
                self.initial_first += profit_f
                self.message_log(f"Reverse cycle profit first {self.profit_first}")
                self.sum_profit_first += self.profit_first
                self.cycle_sell_count += 1
            else:
                self.profit_second += self.round_truncate(self.sum_amount_second - self.reverse_init_amount +
                                                          self.tp_part_amount_second, base=False)
                profit_s = self.round_truncate(self.profit_second - self.tp_part_amount_second, base=False)
                self.deposit_second += profit_s
                self.initial_second += profit_s
                self.message_log(f"Reverse cycle profit second {self.profit_second}")
                self.sum_profit_second += self.profit_second
                self.cycle_buy_count += 1
            self.cycle_time_reverse = None
            self.reverse_target_amount = O_DEC
            self.reverse_init_amount = O_DEC
            self.initial_reverse_first = self.initial_reverse_second = O_DEC
            self.command = 'stop' if REVERSE_STOP and REVERSE else self.command
            if (self.cycle_buy and self.profit_first <= 0) or (not self.cycle_buy and self.profit_second <= 0):
                self.message_log("Strategy have a negative cycle result, STOP", log_level=LogLevel.CRITICAL)
                self.command = 'end'
        else:
            try:
                adx = self.adx(ADX_CANDLE_SIZE_IN_MINUTES, ADX_NUMBER_OF_CANDLES, ADX_PERIOD)
            except (ZeroDivisionError, statistics.StatisticsError):
                trend_up = True
                trend_down = True
            else:
                trend_up = adx.get('adx') > ADX_THRESHOLD and adx.get('+DI') > adx.get('-DI')
                trend_down = adx.get('adx') > ADX_THRESHOLD and adx.get('-DI') > adx.get('+DI')
                # print('adx: {}, +DI: {}, -DI: {}'.format(adx.get('adx'), adx.get('+DI'), adx.get('-DI')))
            self.cycle_time_reverse = self.cycle_time or datetime.utcnow()
            self.start_reverse_time = self.get_time()
            # Calculate target return amount
            tp = self.calc_profit_order(not self.cycle_buy)
            if self.cycle_buy:
                self.deposit_first = self.round_truncate(self.sum_amount_first, base=True) - self.tp_part_amount_first
                self.reverse_target_amount = tp.get('amount') * tp.get('price') - self.tp_part_amount_second
                self.reverse_init_amount = self.sum_amount_second - self.tp_part_amount_second
                self.initial_reverse_first = self.initial_first + self.sum_amount_first
                self.initial_reverse_second = self.initial_second - self.sum_amount_second
                self.message_log(f"Depo for Reverse cycle first: {self.deposit_first}", log_level=LogLevel.DEBUG,
                                 color=Style.B_WHITE)
            else:
                self.deposit_second = (self.round_truncate(self.sum_amount_second, base=False)
                                       - self.tp_part_amount_second)
                self.reverse_target_amount = tp.get('amount') - self.tp_part_amount_first
                self.reverse_init_amount = self.sum_amount_first - self.tp_part_amount_first
                self.initial_reverse_first = self.initial_first - self.sum_amount_first
                self.initial_reverse_second = self.initial_second + self.sum_amount_second
                self.message_log(f"Depo for Reverse cycle second: {self.deposit_second}", log_level=LogLevel.DEBUG,
                                 color=Style.B_WHITE)
            self.message_log(f"Actual depo for initial cycle was: {self.reverse_init_amount}", log_level=LogLevel.DEBUG)
            self.message_log(f"For Reverse cycle set target return amount: {self.reverse_target_amount}"
                             f" with profit: {tp.get('profit')}%", color=Style.B_WHITE)
            self.debug_output()
            if (self.cycle_buy and trend_down) or (not self.cycle_buy and trend_up):
                self.message_log('Start reverse cycle', tlg=True)
                self.reverse = True
                self.command = 'stop' if REVERSE_STOP else None
            else:
                self.message_log('Hold reverse cycle', color=Style.B_WHITE)
                self.reverse_price = self.get_buffered_ticker().last_price
                self.reverse_hold = True
                self.place_profit_order()
        if not self.reverse_hold:
            # Reverse
            self.cycle_buy = not self.cycle_buy
            self.sum_amount_first = self.tp_part_amount_first
            self.sum_amount_second = self.tp_part_amount_second
            self.tp_part_amount_first = self.tp_part_amount_second = O_DEC
            self.debug_output()
            self.start(profit_f, profit_s)

    def place_grid_part(self) -> None:
        if not self.grid_remove:
            self.grid_place_flag = True
            n = len(self.orders_grid) + len(self.orders_init)
            if n < ORDER_Q:
                self.message_log(f"Place next part of grid orders, hold {len(self.orders_hold)}", color=Style.B_WHITE)
                k = 0
                for i in self.orders_hold:
                    if k == GRID_MAX_COUNT or k + n >= ORDER_Q:
                        if k + n >= ORDER_Q:
                            self.order_q_placed = True
                        break
                    waiting_order_id = self.place_limit_order_check(
                        i['buy'],
                        i['amount'],
                        i['price'],
                        check=True,
                        price_limit_rules=True
                    )
                    if waiting_order_id:
                        self.orders_init.append_order(waiting_order_id, i['buy'], i['amount'], i['price'])
                        k += 1
                    else:
                        break
                del self.orders_hold.orders_list[:k]

    def grid_only_stop(self) -> None:
        tcm = self.get_trading_capability_manager()
        avg_rate = tcm.round_price(self.sum_amount_second / self.sum_amount_first, ROUND_FLOOR)
        if self.cycle_buy:
            self.message_log(f"End buy asset cycle\n"
                             f"Sell {self.sum_amount_second} {self.s_currency}\n"
                             f"Buy {self.sum_amount_first} {self.f_currency}\n"
                             f"Average rate is {avg_rate}", tlg=True)
        else:
            self.message_log(f"End sell asset cycle\n"
                             f"Buy {self.sum_amount_second} {self.s_currency}\n"
                             f"Sell {self.sum_amount_first} {self.f_currency}\n"
                             f"Average rate is {avg_rate}", tlg=True)
        self.sum_amount_first = self.sum_amount_second = O_DEC
        if USE_ALL_FUND:
            self.grid_only_restart = True
            self.message_log("Waiting funding for convert", color=Style.B_WHITE)
            return
        self.command = 'stop'

    def grid_handler(
        self,
        _amount_first=None,
        _amount_second=None,
        by_market=False,
        after_full_fill=True,
        order_id=None
    ) -> None:
        """
        Handler after filling grid order
        """
        if after_full_fill and _amount_first:
            # Calculate trade amount with Fee
            amount_first_fee, amount_second_fee = self.fee_for_grid(_amount_first, _amount_second, by_market)
            # Get partially filled amount
            if order_id:
                part_amount = self.part_amount.pop(order_id, (O_DEC, O_DEC))
            else:
                part_amount = (O_DEC, O_DEC)
            # Calculate cycle sum trading for both currency
            delta_f = amount_first_fee + part_amount[0]
            delta_s = amount_second_fee + part_amount[1]
            self.sum_amount_first += delta_f
            self.sum_amount_second += delta_s
            self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                             f" Sum_amount_second: {self.sum_amount_second}",
                             log_level=LogLevel.DEBUG, color=Style.MAGENTA)
            if GRID_ONLY:
                # Correct depo and init amount
                if self.cycle_buy:
                    self.deposit_second -= delta_s
                    self.initial_first += delta_f
                    self.initial_second -= delta_s
                else:
                    self.deposit_first -= delta_f
                    self.initial_first -= delta_f
                    self.initial_second += delta_s
        # State
        no_grid = not self.orders_grid and not self.orders_hold and not self.orders_init
        if no_grid and not self.orders_save:
            if self.tp_order_id:
                self.tp_hold = False
                self.tp_cancel_from_grid_handler = True
                if not self.cancel_order_id:
                    self.cancel_order_id = self.tp_order_id
                    self.cancel_order_exp(self.tp_order_id)
                return
            if self.tp_wait_id:
                # Wait tp order and cancel in on_cancel_order_success and restart
                self.tp_cancel_from_grid_handler = True
                return
            if GRID_ONLY:
                self.shift_grid_threshold = None
                self.grid_only_stop()
            elif self.tp_part_amount_first and self.convert_tp(
                    self.tp_part_amount_first,
                    self.tp_part_amount_second,
                    _update_sum_amount=False):
                self.message_log("No grid orders after part filled TP, converted TP to grid", tlg=True)
                self.tp_part_amount_first = self.tp_part_amount_second = O_DEC
            elif self.tp_was_filled:
                self.message_log("Was filled TP and all grid orders, converse TP to grid", tlg=True)
                self.after_filled_tp(one_else_grid=True)
            else:
                # Ended grid order, calculate depo and Reverse
                self.reverse_after_grid_ending()
        else:
            if self.orders_save and not self.restore_orders:
                self.start_hold = False
                self.restore_orders = True
                self.message_log("Restore deleted and unplaced grid orders")
                try:
                    Strategy.bulk_orders_cancel.clear()
                except AttributeError:
                    self.message_log("grid_handler: AttributeError raised", LogLevel.WARNING)

            if after_full_fill and self.orders_hold and self.order_q_placed and not self.grid_remove:
                # PLace one hold grid order and remove it from hold list
                _, _buy, _amount, _price = self.orders_hold.get_first()
                check = (len(self.orders_grid) + len(self.orders_hold)) <= 2
                waiting_order_id = self.place_limit_order_check(
                    _buy,
                    _amount,
                    _price,
                    check=check,
                    price_limit_rules=True
                )
                if waiting_order_id:
                    self.orders_init.append_order(waiting_order_id, _buy, _amount, _price)
                    del self.orders_hold.orders_list[0]
            # Exist filled but non processing TP
            if self.tp_was_filled:
                self.after_filled_tp(one_else_grid=True)
            else:
                self.place_profit_order(by_market)

    def convert_tp(self, _amount_f: Decimal, _amount_s: Decimal, _update_sum_amount=True) -> bool:
        self.message_log(f"Converted TP amount to grid: first: {_amount_f}, second: {_amount_s}")
        if _update_sum_amount:
            # Correction sum_amount
            self.update_sum_amount(_amount_f, _amount_s)
        # Return depo in turnover without loss
        reverse_target_amount = O_DEC
        if self.cycle_buy:
            amount = _amount_s
            if self.reverse:
                reverse_target_amount = self.reverse_target_amount * _amount_f / self.reverse_init_amount
        else:
            amount = _amount_f
            if self.reverse:
                reverse_target_amount = self.reverse_target_amount * _amount_s / self.reverse_init_amount

        self.message_log(f"For additional {'Buy' if self.cycle_buy else 'Sell'}"
                         f"{' Reverse' if self.reverse else ''} grid amount: {amount}",
                         tlg=True)
        if self.check_min_amount(amount=_amount_f):
            self.message_log("Place additional grid orders and replace TP", tlg=True)
            self.tp_hold_additional = True
            self.place_grid(self.cycle_buy,
                            amount,
                            reverse_target_amount,
                            allow_grid_shift=False,
                            additional_grid=True)
            return True
        if self.orders_hold:
            self.message_log("Small amount was added to last held grid order", tlg=True)
            _order = list(self.orders_hold.get_last())
            _order[2] += (amount / _order[3]) if self.cycle_buy else amount
            self.orders_hold.remove(_order[0])
            self.orders_hold.append_order(*_order)
            return True

        if self.orders_grid:
            self.message_log("Small amount was added to last grid order", tlg=True)
            _order = list(self.orders_grid.get_last())
            _order_updated = self.get_buffered_open_order(_order[0])
            _order[2] = _order_updated.remaining_amount + ((amount / _order[3]) if self.cycle_buy else amount)
            self.cancel_grid_order_id = _order[0]
            self.cancel_order(_order[0])
            self.orders_hold.append_order(*_order)
            return True

        self.message_log("Too small for trade and not grid for update", tlg=True)
        return False

    def update_sum_amount(self, _amount_f, _amount_s):
        self.message_log(f"Before Correction: Sum_amount_first: {self.sum_amount_first},"
                         f" Sum_amount_second: {self.sum_amount_second}",
                         log_level=LogLevel.DEBUG, color=Style.MAGENTA)
        self.sum_amount_first -= _amount_f
        self.sum_amount_second -= _amount_s
        self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                         f" Sum_amount_second: {self.sum_amount_second}",
                         log_level=LogLevel.DEBUG, color=Style.MAGENTA)

    def cancel_grid(self, cancel_all=False):
        """
        Atomic cancel grid orders. Before start() all grid orders must be confirmed canceled
        """
        if self.grid_remove is None:
            self.grid_remove = True
            if cancel_all:
                self.orders_save.orders_list.clear()
                self.orders_save.orders_list.extend(self.orders_grid)
            self.message_log("cancel_grid: Started", log_level=LogLevel.DEBUG)
        if self.grid_remove:
            if self.orders_init:
                # Exist not accepted grid order(s), wait msg from exchange
                self.start_hold = True
            elif self.orders_grid:
                # Sequential removal orders from grid and make this 'atomic'
                # - on_cancel_order_success: save canceled order to orders_save
                _id, _, _, _ = self.orders_grid.get_first()
                if not cancel_all:
                    self.orders_save.orders_list.append(self.orders_grid.get_by_id(_id))
                self.message_log(f"cancel_grid order: {_id}", log_level=LogLevel.DEBUG)
                self.cancel_order_exp(_id, cancel_all=cancel_all)
            else:
                self.message_log("cancel_grid: Ended", log_level=LogLevel.DEBUG)
                self.orders_save.orders_list.clear()
                self.orders_hold.orders_list.clear()
                self.grid_remove = None
                self.order_q_placed = None
                if self.tp_was_filled:
                    self.grid_update_started = None
                    self.after_filled_tp(one_else_grid=False)
                elif self.grid_update_started:
                    _depo = self.depo_unused()
                    self.message_log(f"Start update grid orders, depo: {_depo}", color=Style.B_WHITE)
                    if self.reverse:
                        if self.cycle_buy:
                            _reverse_target_amount = self.reverse_target_amount - self.sum_amount_first
                        else:
                            _reverse_target_amount = self.reverse_target_amount - self.sum_amount_second
                    else:
                        _reverse_target_amount = O_DEC

                    self.place_grid(self.cycle_buy,
                                    _depo,
                                    _reverse_target_amount,
                                    allow_grid_shift=False,
                                    grid_update=True)
                else:
                    self.grid_update_started = None
                    self.start()
        else:
            self.grid_remove = None

    def check_min_amount(self, amount=O_DEC, price=O_DEC, for_tp=True) -> bool:
        _price = price or self.avg_rate

        if not _price:
            return False

        _amount = amount
        tcm = self.get_trading_capability_manager()
        if self.cycle_buy:
            min_trade_amount = tcm.get_min_sell_amount(_price)
            if not _amount:
                _amount = self.sum_amount_first if for_tp else (self.deposit_second / _price)
        else:
            min_trade_amount = tcm.get_min_buy_amount(_price)
            if not _amount:
                _amount = (self.sum_amount_second / _price) if for_tp else self.deposit_first

        _amount = self.round_truncate(_amount, base=True)
        return _amount >= min_trade_amount

    def place_limit_order_check(
            self,
            buy: bool,
            amount: Decimal,
            price: Decimal,
            check=False,
            price_limit_rules=False
    ) -> int:
        """
        Before place limit order check trade conditions and correct price
        """
        if price_limit_rules:
            tcm = self.get_trading_capability_manager()
            _price = self.get_buffered_ticker().last_price or self.avg_rate
            if ((buy and price < tcm.get_min_buy_price(_price)) or
                    (not buy and price > tcm.get_max_sell_price(_price))):
                self.message_log(
                    f"{'Buy' if buy else 'Sell'} price {price} is out of trading range, will try later",
                    log_level=LogLevel.WARNING,
                    color=Style.YELLOW
                )
                return 0
        _price = price
        if check:
            order_book = self.get_buffered_order_book()
            if buy and order_book.bids:
                price = min(_price, order_book.bids[0].price)
            elif not buy and order_book.asks:
                price = max(_price, order_book.asks[0].price)

        waiting_order_id = self.place_limit_order(buy, amount, price)
        if _price != price:
            self.message_log(f"For order {waiting_order_id} price was updated from {_price} to {price}",
                             log_level=LogLevel.WARNING)
        return waiting_order_id

    ##############################################################
    # public data update methods
    ##############################################################
    def on_new_ticker(self, ticker: Ticker) -> None:
        # print(f"on_new_ticker:{datetime.fromtimestamp(ticker.timestamp/1000)}: last_price: {ticker.last_price}")
        self.last_ticker_update = int(self.get_time())
        if not self.orders_grid and not self.orders_init and self.orders_hold:
            _, _buy, _amount, _price = self.orders_hold.get_first()
            tcm = self.get_trading_capability_manager()
            if ((_buy and _price >= tcm.get_min_buy_price(ticker.last_price)) or
                    (not _buy and _price <= tcm.get_max_sell_price(ticker.last_price))):
                waiting_order_id = self.place_limit_order_check(
                    _buy,
                    _amount,
                    _price,
                    check=True
                )
                self.orders_init.append_order(waiting_order_id, _buy, _amount, _price)
                del self.orders_hold.orders_list[0]
        #
        if (self.shift_grid_threshold and self.last_shift_time and self.get_time() -
                self.last_shift_time > SHIFT_GRID_DELAY
            and ((self.cycle_buy and ticker.last_price >= self.shift_grid_threshold)
                 or
                 (not self.cycle_buy and ticker.last_price <= self.shift_grid_threshold))):
            self.message_log('Shift grid', color=Style.B_WHITE)
            self.shift_grid_threshold = None
            self.start_after_shift = True
            if self.part_amount:
                self.message_log("Grid order was small partially filled, correct depo")
                _k, part_amount = self.part_amount.popitem()
                if self.cycle_buy:
                    part_amount_second = self.round_truncate(part_amount[1], base=False)
                    self.deposit_second += part_amount_second
                    if self.reverse:
                        self.initial_reverse_second += part_amount_second
                    else:
                        self.initial_second += part_amount_second
                    self.message_log(f"New second depo: {self.deposit_second}")
                else:
                    part_amount_first = self.round_truncate(part_amount[0], base=True)
                    self.deposit_first += part_amount_first
                    if self.reverse:
                        self.initial_reverse_first += part_amount_first
                    else:
                        self.initial_first += part_amount_first
                    self.message_log(f"New first depo: {self.deposit_first}")
            self.grid_remove = None
            self.cancel_grid(cancel_all=True)

    def on_new_order_book(self, order_book: OrderBook) -> None:
        # print(f"on_new_order_book: max_bids: {order_book.bids[0].price}, min_asks: {order_book.asks[0].price}")
        pass

    ##############################################################
    # private update methods
    ##############################################################

    def on_balance_update(self, balance: Dict) -> None:
        asset = balance['asset']
        delta = Decimal(balance['balance_delta'])
        restart = False
        if delta > 0:
            delta = self.round_truncate(delta, bool(asset == self.f_currency), _rounding=ROUND_FLOOR)
        else:
            delta = self.round_truncate(delta, bool(asset == self.f_currency), _rounding=ROUND_CEILING)
        #
        if self.cycle_buy:
            if asset == self.s_currency:
                restart = True
                if self.reverse:
                    if delta < 0 and abs(delta) > self.initial_reverse_second - self.deposit_second:
                        self.deposit_second = self.initial_reverse_second + delta
                    elif delta > 0:
                        self.deposit_second += delta
                    self.initial_reverse_second += delta
                else:
                    if delta < 0 and abs(delta) > self.initial_second - self.deposit_second:
                        self.deposit_second = self.initial_second + delta
                    elif delta > 0:
                        self.deposit_second += delta
                    self.initial_second += delta
            elif asset == self.f_currency and not GRID_ONLY:
                self.initial_first += delta
                if self.reverse:
                    self.initial_reverse_first += delta
        else:
            if asset == self.f_currency:
                restart = True
                if self.reverse:
                    if delta < 0 and abs(delta) > self.initial_reverse_first - self.deposit_first:
                        self.deposit_first = self.initial_reverse_first + delta
                    elif delta > 0:
                        self.deposit_first += delta
                    self.initial_reverse_first += delta
                else:
                    if delta < 0 and abs(delta) > self.initial_first - self.deposit_first:
                        self.deposit_first = self.initial_first + delta
                    elif delta > 0:
                        self.deposit_first += delta
                    self.initial_first += delta
            elif asset == self.s_currency and not GRID_ONLY:
                self.initial_second += delta
                if self.reverse:
                    self.initial_reverse_second += delta
        self.message_log(f"Was {'depositing' if delta > 0 else 'transferring (withdrawing)'} {delta} {asset}",
                         color=Style.UNDERLINE, tlg=True)
        if (self.grid_only_restart or (GRID_ONLY and USE_ALL_FUND)) and restart:
            self.restart = True
            self.grid_only_restart = None
            self.grid_remove = None
            self.cancel_grid(cancel_all=True)

    def on_new_funds(self, funds: Dict[str, FundsEntry]) -> None:
        # print(f"on_new_funds.funds: {funds}")
        ff = funds.get(self.f_currency, O_DEC)
        fs = funds.get(self.s_currency, O_DEC)
        if self.wait_refunding_for_start:
            ff = ff.total_for_currency if ff else O_DEC
            fs = fs.total_for_currency if fs else O_DEC
            if self.cycle_buy:
                go_trade = fs >= (self.initial_reverse_second if self.reverse else self.initial_second)
            else:
                go_trade = ff >= (self.initial_reverse_first if self.reverse else self.initial_first)
            if go_trade:
                self.message_log("Started after receipt of funds")
                self.start()
                return
        if self.tp_order_hold:
            if self.tp_order_hold['buy_side']:
                available_fund = fs.available if fs else O_DEC
            else:
                available_fund = ff.available if ff else O_DEC
            if available_fund >= self.tp_order_hold['amount']:
                self.place_profit_order(by_market=self.tp_order_hold['by_market'])
                return
        if self.grid_hold:
            if self.grid_hold['buy_side']:
                available_fund = fs.available if fs else O_DEC
            else:
                available_fund = ff.available if ff else O_DEC
            if available_fund >= self.grid_hold['depo']:
                self.place_grid(self.grid_hold['buy_side'],
                                self.grid_hold['depo'],
                                self.grid_hold['reverse_target_amount'],
                                self.grid_hold['allow_grid_shift'],
                                self.grid_hold['additional_grid'],
                                self.grid_hold['grid_update'])

    def on_order_update(self, update: OrderUpdate) -> None:
        # self.message_log(f"Order {update.original_order.id}: {update.status}", log_level=LogLevel.DEBUG)
        if update.status in [OrderUpdate.ADAPTED,
                             OrderUpdate.NO_CHANGE,
                             OrderUpdate.REAPPEARED,
                             OrderUpdate.DISAPPEARED,
                             OrderUpdate.CANCELED,
                             OrderUpdate.OTHER_CHANGE]:
            return
        #
        self.message_log(f"Order {update.original_order.id}: {update.status}", color=Style.B_WHITE)
        result_trades = update.resulting_trades
        amount_first = amount_second = O_DEC
        if update.status == OrderUpdate.PARTIALLY_FILLED:
            # Get last trade row
            if result_trades:
                i = result_trades[-1]
                amount_first = i.amount
                amount_second = i.amount * i.price
                self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
            else:
                self.message_log(f"No records for {update.original_order.id}", log_level=LogLevel.WARNING)
        else:
            for i in result_trades:
                # Calculate sum trade amount for both currency
                amount_first += i.amount
                amount_second += i.amount * i.price
                self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
        # Retreat of courses
        self.avg_rate = amount_second / amount_first
        self.message_log(f"Executed amount: First: {amount_first}, Second: {amount_second}, price: {self.avg_rate}")
        if update.status in (OrderUpdate.FILLED, OrderUpdate.ADAPTED_AND_FILLED):
            if not GRID_ONLY:
                self.shift_grid_threshold = None
            if self.orders_grid.exist(update.original_order.id):
                self.ts_grid_update = self.get_time()
                # Remove grid order with =id from order list
                self.orders_grid.remove(update.original_order.id)
                if self.orders_save:
                    self.orders_save.remove(update.original_order.id)
                    if not self.orders_save:
                        self.restore_orders = False
                self.grid_handler(_amount_first=amount_first,
                                  _amount_second=amount_second,
                                  after_full_fill=True,
                                  order_id=update.original_order.id)
            elif self.tp_order_id == update.original_order.id:
                # Filled take profit order, restart
                self.tp_order_id = None
                self.cancel_order_id = None
                self.tp_order = ()
                if self.reverse_hold:
                    self.cancel_reverse_hold()
                if self.tp_part_amount_first:
                    self.update_sum_amount(- self.tp_part_amount_first, - self.tp_part_amount_second)
                    self.tp_part_amount_first = self.tp_part_amount_second = O_DEC
                    self.tp_part_free = False
                self.tp_was_filled = (amount_first, amount_second, False)
                # print(f"on_order_update.was_filled_tp: {self.tp_was_filled}")
                if self.tp_hold:
                    # After place but before execute TP was filled some grid
                    self.tp_hold = False
                    self.after_filled_tp(one_else_grid=True)
                elif self.tp_cancel_from_grid_handler:
                    self.tp_cancel_from_grid_handler = False
                    self.grid_handler()
                else:
                    self.restore_orders = False
                    self.cancel_grid(cancel_all=True)
            else:
                self.message_log('Wild order, do not know it', tlg=True)
        elif update.status == OrderUpdate.PARTIALLY_FILLED:
            if self.tp_order_id == update.original_order.id:
                self.message_log("Take profit partially filled", color=Style.B_WHITE)
                amount_first_fee, amount_second_fee = self.fee_for_tp(amount_first, amount_second)
                # Calculate profit for filled part TP
                _profit_first = _profit_second = O_DEC
                if self.cycle_buy:
                    _, target_fee = self.fee_for_tp(O_DEC, self.tp_target, log_output=False)
                    _profit_second = self.round_truncate(((target_fee - self.tp_amount) * amount_second_fee /
                                                          target_fee), base=False)
                    self.part_profit_second += _profit_second
                    self.message_log(f"Part profit second {self.part_profit_second}", log_level=LogLevel.DEBUG)
                else:
                    target_fee, _ = self.fee_for_tp(self.tp_target, O_DEC, log_output=False)
                    _profit_first = self.round_truncate(((target_fee - self.tp_amount) * amount_first_fee /
                                                         target_fee), base=True)
                    self.part_profit_first += _profit_first
                    self.message_log(f"Part profit first {self.part_profit_first}", log_level=LogLevel.DEBUG)
                self.tp_part_amount_first += amount_first_fee - _profit_first
                self.tp_part_amount_second += amount_second_fee - _profit_second
                self.tp_part_free = True
                self.update_sum_amount(amount_first_fee - _profit_first, amount_second_fee - _profit_second)
                if self.reverse_hold:
                    self.start_reverse_time = self.get_time()
                    if self.convert_tp(self.tp_part_amount_first,
                                       self.tp_part_amount_second,
                                       _update_sum_amount=False):
                        self.cancel_reverse_hold()
                        self.tp_part_free = False
                        self.message_log("Part filled TP was converted to grid", tlg=True)
            else:
                self.message_log("Grid order partially filled", color=Style.B_WHITE)
                self.ts_grid_update = self.get_time()
                amount_first_fee, amount_second_fee = self.fee_for_grid(amount_first, amount_second)
                # Correction amount for saved order, if exists
                if _order := self.orders_save.get_by_id(update.original_order.id):
                    self.orders_save.remove(update.original_order.id)
                    _order['amount'] -= amount_first
                    self.orders_save.orders_list.append(_order)
                # Increase trade result and if next fill order is grid decrease trade result
                self.sum_amount_first += amount_first_fee
                self.sum_amount_second += amount_second_fee
                self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                                 f" Sum_amount_second: {self.sum_amount_second}",
                                 log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                part_amount_first, part_amount_second = self.part_amount.pop(update.original_order.id, (O_DEC, O_DEC))
                part_amount_first -= amount_first_fee
                part_amount_second -= amount_second_fee
                self.part_amount[update.original_order.id] = (part_amount_first, part_amount_second)
                self.message_log(f"Part_amount_first: {part_amount_first},"
                                 f" Part_amount_second: {part_amount_second}", log_level=LogLevel.DEBUG)
                if GRID_ONLY:
                    # Correct depo and init amount
                    if self.cycle_buy:
                        self.deposit_second -= amount_second_fee
                        self.initial_first += amount_first_fee
                        self.initial_second -= amount_second_fee
                    else:
                        self.deposit_first -= amount_first_fee
                        self.initial_first -= amount_first_fee
                        self.initial_second += amount_second_fee
                else:
                    # Get min trade amount
                    if self.check_min_amount():
                        self.shift_grid_threshold = None
                        self.grid_handler(after_full_fill=False)
                    else:
                        self.last_shift_time = self.get_time() + 2 * SHIFT_GRID_DELAY
                        self.message_log("Partially trade too small, ignore", color=Style.B_WHITE)

    def cancel_reverse_hold(self):
        self.reverse_hold = False
        self.cycle_time_reverse = None
        self.reverse_target_amount = O_DEC
        self.reverse_init_amount = O_DEC
        self.initial_reverse_first = self.initial_reverse_second = O_DEC
        self.message_log("Cancel hold reverse cycle", color=Style.B_WHITE, tlg=True)

    def on_place_order_success(self, place_order_id: int, order: Order) -> None:
        # print(f"on_place_order_success.place_order_id: {place_order_id}")
        if order.amount > order.received_amount > 0:
            self.message_log(f"Order {place_order_id} was partially filled", color=Style.B_WHITE)
            self.shift_grid_threshold = None
        if order.remaining_amount == 0:
            self.shift_grid_threshold = None
            # Get actual parameter of last trade order
            market_order = self.get_buffered_completed_trades()
            amount_first = amount_second = O_DEC
            self.message_log(f"Order {place_order_id} executed by market", color=Style.B_WHITE)
            for o in market_order:
                if o.order_id == order.id:
                    amount_first += o.amount
                    amount_second += o.amount * o.price
            if not amount_first:
                amount_first += order.amount
                amount_second += order.amount * order.price
            self.avg_rate = amount_second / amount_first
            self.message_log(f"For {order.id} first: {float(amount_first):f},"
                             f" second: {float(amount_second):f}, price: {float(self.avg_rate):f}")
            if self.orders_init.exist(place_order_id):
                self.ts_grid_update = self.get_time()
                self.message_log(f"Grid order {order.id} execute by market")
                self.orders_init.remove(place_order_id)
                self.message_log(f"Waiting order count is: {len(self.orders_init)}, hold: {len(self.orders_hold)}")
                # Place take profit order
                self.grid_handler(
                    _amount_first=amount_first,
                    _amount_second=amount_second,
                    by_market=True,
                    after_full_fill=True
                )
            elif place_order_id == self.tp_wait_id:
                # Take profit order execute by market, restart
                self.tp_wait_id = None
                if self.reverse_hold:
                    self.cancel_reverse_hold()
                self.message_log(f"Take profit order {order.id} execute by market")
                self.tp_was_filled = (amount_first, amount_second, True)
                if self.tp_hold or self.tp_cancel_from_grid_handler:
                    self.tp_cancel_from_grid_handler = False
                    self.tp_hold = False
                    # After place but before accept TP was filled some grid
                    self.after_filled_tp(one_else_grid=True)
                else:
                    self.restore_orders = False
                    self.cancel_grid(cancel_all=True)
            else:
                self.message_log(f"Did not have waiting order id for {place_order_id}", LogLevel.ERROR,
                                 color=Style.B_RED)
        else:
            if self.orders_init.exist(place_order_id):
                self.ts_grid_update = self.get_time()
                self.orders_grid.append_order(order.id, order.buy, order.amount, order.price)
                self.orders_grid.sort(self.cycle_buy)
                self.orders_init.remove(place_order_id)
                if not self.orders_init:
                    self.last_shift_time = self.get_time()
                    if GRID_ONLY and self.orders_hold:
                        # Place next part of grid orders
                        self.place_grid_part()
                    else:
                        if self.grid_place_flag or not self.orders_hold:
                            if self.orders_hold:
                                self.message_log(f"Part of grid orders are placed. Left: {len(self.orders_hold)}",
                                                 color=Style.B_WHITE)
                            else:
                                self.order_q_placed = True
                                self.message_log('All grid orders place successfully', color=Style.B_WHITE)
                        elif not self.order_q_placed and not self.shift_grid_threshold:
                            self.place_grid_part()
                        if self.start_hold:
                            self.message_log('Release hold Start, continue remove grid orders', color=Style.B_WHITE)
                            self.start_hold = False
                            self.cancel_grid()
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None
                self.tp_order_id = order.id
                if self.tp_hold or self.tp_cancel or self.tp_cancel_from_grid_handler:
                    self.cancel_order_id = self.tp_order_id
                    self.cancel_order_exp(self.tp_order_id)
                else:
                    # Place next part of grid orders
                    if self.orders_hold and not self.order_q_placed and not self.orders_init:
                        self.place_grid_part()
            else:
                self.message_log(f"Did not have waiting order id for {place_order_id}", LogLevel.ERROR)

    def on_place_order_error_string(self, place_order_id: int, error: str) -> None:
        # Check all orders on exchange if exists required
        self.message_log(f"On place order {place_order_id} error: {error}", LogLevel.ERROR, tlg=True)
        open_orders = self.get_buffered_open_orders()
        order = None
        if self.orders_init.exist(place_order_id):
            order = self.orders_init.find_order(open_orders, place_order_id)
        elif place_order_id == self.tp_wait_id:
            for k, o in enumerate(open_orders):
                if (o.buy == self.tp_order[0] and
                        o.amount == self.tp_order[1] and
                        o.price == self.tp_order[2]):
                    order = open_orders[k]
        if order:
            self.message_log(f"Order {place_order_id} placed", tlg=True)
            self.on_place_order_success(place_order_id, order)
        else:
            self.message_log(f"Trying place order {place_order_id} one more time", tlg=True)
            if self.orders_init.exist(place_order_id):
                _order = self.orders_init.get_by_id(place_order_id)
                self.orders_init.remove(place_order_id)
                waiting_order_id = self.place_limit_order_check(
                    _order['buy'],
                    _order['amount'],
                    _order['price'],
                    check=True,
                    price_limit_rules=True
                )
                if waiting_order_id:
                    _order['id'] = waiting_order_id
                    self.orders_init.orders_list.append(_order)
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None
                self.tp_error = True

    def on_cancel_order_success(self, order_id: int, cancel_all=False) -> None:
        if order_id == self.cancel_grid_order_id:
            self.ts_grid_update = self.get_time()
            self.cancel_grid_order_id = None
            self.message_log(f"Processing updated grid order {order_id}", log_level=LogLevel.INFO)
            self.orders_grid.remove(order_id)
        elif self.orders_grid.exist(order_id):
            self.message_log(f"Processing canceled grid order {order_id}", log_level=LogLevel.INFO)
            self.ts_grid_update = self.get_time()
            self.part_amount.pop(order_id, None)
            self.orders_grid.remove(order_id)
            if self.restore_orders:
                if _order := self.orders_save.get_by_id(order_id):
                    self.orders_save.remove(order_id)
                    if self.check_min_amount(amount=_order['amount'], price=_order['price']):
                        self.orders_hold.orders_list.append(_order)
                    elif self.orders_save:
                        _order_saved = list(self.orders_save.get_last())
                        _order_saved[2] += _order['amount']
                        self.orders_save.remove(_order_saved[0])
                        self.orders_save.append_order(*_order_saved)
                        self.message_log(f"Small restored amount {_order['amount']} was added"
                                         f" to last saved order {_order_saved[0]}", tlg=True)
                    elif self.orders_hold:
                        _order_hold = list(self.orders_hold.get_last())
                        _order_hold[2] += _order['amount']
                        self.orders_hold.remove(_order_hold[0])
                        self.orders_hold.append_order(*_order_hold)
                        self.message_log(f"Small restored amount {_order['amount']} was added"
                                         f" to last held order {_order_hold[0]}", tlg=True)
                    else:
                        self.message_log("Too small restore for trade and not saved or held grid for update", tlg=True)
                if not self.orders_save:
                    self.restore_orders = False
                    self.orders_hold.sort(self.cycle_buy)
                    self.grid_remove = None
                    self.order_q_placed = False
                    self.place_profit_order()
            elif self.grid_remove:
                self.cancel_grid(cancel_all=cancel_all)
        elif order_id == self.cancel_order_id:
            self.message_log(f"Processing canceled TP order {order_id}")
            self.cancel_order_id = None
            self.tp_order_id = None
            self.tp_order = ()
            if self.tp_part_amount_first:
                self.message_log(f"Partially filled TP order {order_id} was canceled")
                if self.tp_part_free:
                    self.convert_tp(self.tp_part_amount_first, self.tp_part_amount_second, _update_sum_amount=False)
                    self.tp_part_free = False
                self.tp_part_amount_first = self.tp_part_amount_second = O_DEC
                # Save part profit
                self.profit_first += self.part_profit_first
                self.profit_second += self.part_profit_second
                self.part_profit_first = self.part_profit_second = O_DEC
            if self.tp_hold:
                self.tp_hold = False
                self.place_profit_order()
                return
            if self.tp_cancel_from_grid_handler:
                self.tp_cancel_from_grid_handler = False
                self.grid_handler()
                return
            if self.tp_cancel:
                # Restart
                self.tp_cancel = False
                self.start()

    def on_cancel_order_error_string(self, order_id: int, error: str) -> None:
        self.message_log(f"On cancel order {order_id} {error}", LogLevel.ERROR)
