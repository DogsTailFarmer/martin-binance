#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Cyclic grid strategy based on martingale
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.0rc2"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################

try:
    from margin_wrapper import *  # lgtm [py/polluting-import]
    from margin_wrapper import __version__ as msb_ver
except ImportError:
    from margin_strategy_sdk import *  # lgtm [py/polluting-import]
    from typing import Dict, List
    import time
    import math
    import os
    import simplejson as json
    import charset_normalizer
    msb_ver = ''
    STANDALONE = False
else:
    STANDALONE = True
#
import gc
import psutil
import sqlite3
import statistics
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from threading import Thread
import queue
import requests

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
EXTRA_CHECK_ORDER_STATE = bool()
# Trade parameter
START_ON_BUY = bool()
AMOUNT_FIRST = Decimal()
USE_ALL_FIRST_FUND = bool()
AMOUNT_SECOND = Decimal()
PRICE_SHIFT = float()
# Round pattern
ROUND_BASE = str()
ROUND_QUOTE = str()
#
PROFIT = Decimal()
PROFIT_MAX = Decimal()
PROFIT_REVERSE = Decimal()
OVER_PRICE = Decimal()
ORDER_Q = int()
MARTIN = Decimal()
SHIFT_GRID_DELAY = int()
# Other
STATUS_DELAY = int()
GRID_ONLY = bool()
LOG_LEVEL_NO_PRINT = []
#
ADAPTIVE_TRADE_CONDITION = bool()
BB_CANDLE_SIZE_IN_MINUTES = int()
BB_NUMBER_OF_CANDLES = int()
KBB = float()
PROFIT_K = float()
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
REVERSE_TARGET_AMOUNT = float()
REVERSE_INIT_AMOUNT = Decimal()
REVERSE_STOP = bool()
# Config variables
HEAD_VERSION = str()
LOAD_LAST_STATE = int()
# Path and files name
LOG_PATH = str()
WORK_PATH = str()
LAST_STATE_PATH = str()
FILE_LAST_STATE = str()
VPS_NAME = str()
# Telegram
TELEGRAM_URL = str()
TOKEN = str()
CHANNEL_ID = str()
# endregion


class Style:
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


def telegram(queue_to_tlg) -> None:
    url = TELEGRAM_URL
    token = TOKEN
    channel_id = CHANNEL_ID
    url += token
    method = url + '/sendMessage'

    def telegram_get(offset=None) -> []:
        command_list = []
        _method = url + '/getUpdates'
        res = None
        try:
            res = requests.post(_method, data={'chat_id': channel_id, 'offset': offset})
        except Exception as _exp:
            print(f"telegram_get: {_exp}")
        if res and res.status_code == 200:
            result = res.json().get('result')
            # print(f"telegram_get.result: {result}")
            message_id = None
            text_in = None
            reply_to_message = None
            for i in result:
                update_id = i.get('update_id')
                message = i.get('message')
                if message:
                    from_id = message.get('from').get('id')
                    if from_id == int(channel_id):
                        message_id = message.get('message_id')
                        text_in = i.get('message').get('text')
                        try:
                            reply_to_message = i.get('message').get('reply_to_message').get('text')
                        except AttributeError:
                            reply_to_message = None
                command_list.append({'update_id': update_id, 'message_id': message_id,
                                     'text_in': text_in, 'reply_to_message': reply_to_message})
        return command_list

    connection_control = sqlite3.connect(WORK_PATH + 'funds_rate.db')
    cursor_control = connection_control.cursor()
    offset_id = None
    while True:
        try:
            text = queue_to_tlg.get(block=True, timeout=10)
        except KeyboardInterrupt:
            break
        except queue.Empty:
            # Get external command from Telegram bot
            x = telegram_get(offset_id)
            if x:
                offset_id = x[-1].get('update_id')
                offset_id += 1
                for n in x:
                    a = n.get('reply_to_message')
                    if a:
                        bot_id = a.split('.')[0]
                        cursor_control.execute('insert into t_control values(?,?,?,?)',
                                               (n['message_id'], n['text_in'], bot_id, None))
                        # Send receipt
                        text = f"{n['text_in']}, OK"
                        try:
                            requests.post(method, data={'chat_id': channel_id, 'text': text})
                        except Exception as _ex:
                            print(f"telegram: {_ex}")
                connection_control.commit()
        else:
            if text and 'stop_signal_QWE#@!' in text:
                break
            try:
                requests.post(method, data={'chat_id': channel_id, 'text': text})
            except Exception as _ex:
                print(f"telegram: {_ex}")
    print("tlg_stop")


def save_to_db(queue_to_db) -> None:
    connection_analytic = sqlite3.connect(WORK_PATH + 'funds_rate.db', check_same_thread=False)
    cursor_analytic = connection_analytic.cursor()
    # Compliance check t_exchange and EXCHANGE() = exchange() from ms_cfg.toml
    cursor_analytic.execute("SELECT id_exchange, name FROM t_exchange")
    row = cursor_analytic.fetchall()
    row_n = len(row)
    for i, exch in enumerate(EXCHANGE):
        if i >= row_n:
            print(f"save_to_db: Add exchange {i}, {exch}")
            cursor_analytic.execute("INSERT into t_exchange values(?,?)", (i, exch))
    connection_analytic.commit()
    # Save data to .db
    data = None
    while True:
        try:
            data = queue_to_db.get()
        except KeyboardInterrupt:
            pass
        if data is None or data.get('stop_signal'):
            break
        print("save_to_db: Record row into .db")
        cursor_analytic.execute("insert into t_funds values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (ID_EXCHANGE,
                                 None,
                                 data.get('f_currency'),
                                 data.get('s_currency'),
                                 float(data.get('f_funds')),
                                 float(data.get('s_funds')),
                                 float(data.get('avg_rate')),
                                 data.get('cycle_buy'),
                                 float(data.get('f_depo')),
                                 float(data.get('s_depo')),
                                 float(data.get('f_profit')),
                                 float(data.get('s_profit')),
                                 datetime.utcnow(),
                                 PRICE_SHIFT,
                                 float(PROFIT),
                                 float(data.get('over_price')),
                                 data.get('order_q'),
                                 float(MARTIN),
                                 LINEAR_GRID_K,
                                 ADAPTIVE_TRADE_CONDITION,
                                 KBB,
                                 PROFIT_K,
                                 data.get('cycle_time')))
        connection_analytic.commit()
    connection_analytic.commit()
    print("db_stop")


def float2decimal(_f: float) -> Decimal:
    return Decimal(str(_f))


class Orders:
    def __init__(self):
        self.orders_list = []

    def __iter__(self):
        for i in self.orders_list:
            yield i

    def __len__(self):
        return len(self.orders_list)

    def append(self, _id: int, buy: bool, amount: Decimal, price: Decimal):
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

    def get_by_id(self, _id: int) -> ():
        for i in self.orders_list:
            if i['id'] == _id:
                return i['buy'], i['amount'], i['price']
        return ()

    def exist(self, _id: int) -> bool:
        for i in self.orders_list:
            if i['id'] == _id:
                return True
        return False

    def get(self) -> []:
        """
        Get List of Dict for orders
        :return: []
        """
        orders = []
        for i in self.orders_list:
            orders.append({'id': i['id'], 'buy': i['buy'], 'amount': i['amount'], 'price': i['price']})
        return orders

    def get_id_list(self) -> []:
        """
        Get List of orders id
        :return: []
        """
        orders = []
        for i in self.orders_list:
            orders.append(i['id'])
        return orders

    def get_first(self) -> ():
        """
        Get [0] Dict for order
        :return: (buy, amount, price)
        """
        return self.orders_list[0]['buy'], self.orders_list[0]['amount'], self.orders_list[0]['price']

    def restore(self, order_list: []):
        self.orders_list.clear()
        for i in order_list:
            i_dec = {'id': i.get('id'),
                     'buy': i.get('buy'),
                     'amount': float2decimal(i.get('amount')),
                     'price': float2decimal(i.get('price'))}
            self.orders_list.append(i_dec)


class Strategy(StrategyBase):
    ##############################################################
    # strategy logic methods
    ##############################################################
    def __init__(self):
        super().__init__()
        print(f"Init Strategy, ver: {HEAD_VERSION} + {__version__} + {msb_ver}")
        self.cycle_buy = not START_ON_BUY if REVERSE else START_ON_BUY  # + Direction (Buy/Sell) for current cycle
        self.orders_grid = Orders()  # + List of grid orders
        self.orders_init = Orders()  # - List of initial grid orders
        self.orders_hold = Orders()  # + List of grid orders for later place
        # Take profit variables
        self.tp_order_id = None  # + Take profit order id
        self.tp_wait_id = None  # -
        self.tp_order = ()  # - (id, buy, amount, price) Placed take profit order
        self.tp_error = False  # Flag when can't place tp
        self.tp_order_hold = {}  # - Save unreleased take profit order
        self.tp_hold = False  # - Flag for replace take profit order
        self.tp_cancel = False  # - Wanted cancel tp order after successes place and Start()
        self.tp_cancel_from_grid_handler = False  # -
        self.tp_hold_additional = False  # - Need place TP after placed additional grid orders
        self.tp_target = Decimal('0')  # + Target amount for TP that will be placed
        self.tp_amount = Decimal('0')  # + Initial depo for active TP
        self.part_profit_first = Decimal('0')  # +
        self.part_profit_second = Decimal('0')  # +
        self.tp_was_filled = ()  # - Exist incomplete processing filled TP
        self.tp_part_amount_first = Decimal('0')  # + Sum partially filled TP
        self.tp_part_amount_second = Decimal('0')  # + Sum partially filled TP
        self.tp_init = (Decimal('0'), Decimal('0'))  # + (sum_amount_first, sum_amount_second) initial amount for TP
        #
        self.sum_amount_first = Decimal('0')  # Sum buy/sell in first currency for current cycle
        self.sum_amount_second = Decimal('0')  # Sum buy/sell in second currency for current cycle
        #
        self.correction_amount_first = Decimal('0')  # +
        self.correction_amount_second = Decimal('0')  # +
        #
        self.deposit_first = AMOUNT_FIRST  # + Calculated operational deposit
        self.deposit_second = AMOUNT_SECOND  # + Calculated operational deposit
        self.sum_profit_first = Decimal('0')  # + Sum profit from start to now()
        self.sum_profit_second = Decimal('0')  # + Sum profit from start to now()
        self.cycle_buy_count = 0  # + Count for buy cycle
        self.cycle_sell_count = 0  # + Count for sale cycle
        self.shift_grid_threshold = None  # - Price level of shift grid threshold for current cycle
        self.f_currency = ''  # - First currency name
        self.s_currency = ''  # - Second currency name
        self.connection_analytic = None  # - Connection to .db
        self.tlg_header = ''  # - Header for Telegram message
        self.last_shift_time = None  # +
        self.avg_rate = Decimal('0')  # - Flow average rate for trading pair
        #
        self.grid_hold = {}  # - Save for later create grid orders
        self.start_hold = False  # - Hold start if exist not accepted grid order(s)
        self.initial_first = Decimal('0')  # + Use if balance replenishment delay
        self.initial_second = Decimal('0')  # + Use if balance replenishment delay
        self.initial_reverse_first = Decimal('0')  # + Use if balance replenishment delay
        self.initial_reverse_second = Decimal('0')  # + Use if balance replenishment delay
        self.wait_refunding_for_start = False  # -
        #
        self.cancel_order_id = None  # - Exist canceled not confirmed order
        self.over_price = None  # + Adaptive over price
        self.grid_place_flag = False  # - Flag when placed next part of grid orders
        self.part_amount_first = Decimal('0')  # + Amount of partially filled order
        self.part_amount_second = Decimal('0')  # + Amount of partially filled order
        self.command = None  # + External input command from Telegram
        self.start_after_shift = False  # - Flag set before shift, clear into Start()
        self.queue_to_db = queue.Queue()  # - Queue for save data to .db
        self.pr_db = None  # - Process for save data to .db
        self.queue_to_tlg = queue.Queue()  # - Queue for sending message to Telegram
        self.pr_tlg = None  # - Process for sending message to Telegram
        self.pr_tlg_control = None  # - Process for get command from Telegram
        self.restart = None  # - Set after execute take profit order and restart cycle
        self.profit_first = Decimal('0')  # + Cycle profit
        self.profit_second = Decimal('0')  # + Cycle profit
        self.status_time = None  # + Last time sending status message
        self.cycle_time = None  # + Cycle start time
        self.cycle_time_reverse = None  # + Reverse cycle start time
        self.reverse = REVERSE  # + Current cycle is Reverse
        self.reverse_target_amount = REVERSE_TARGET_AMOUNT if REVERSE else None  # + Return amount for reverse cycle
        self.reverse_init_amount = REVERSE_INIT_AMOUNT if REVERSE else Decimal('0')  # + Actual amount of initial cycle
        self.reverse_hold = False  # + Exist unreleased reverse state
        self.reverse_price = None  # + Price when execute last grid order and hold reverse cycle
        self.round_base = '1.0123456789'  # - Round pattern for 0.00000 = 0.00
        self.round_quote = '1.0123456789'  # - Round pattern for 0.00000 = 0.00
        self.order_q = None  # + Adaptive order quantity
        self.order_q_placed = False  # - Flag initial number of orders placed
        self.martin = Decimal(0)  # + Operational increment volume of orders in the grid
        self.orders_save = Orders()  # + Save for cancel time
        self.first_run = True  # -
        self.grid_remove = None  # - Flag when starting cancel grid orders
        self.heartbeat_counter = 0  # -
        self.grid_order_canceled = None  # -

    # noinspection PyProtectedMember
    def init(self, check_funds: bool = True) -> None:  # skipcq: PYL-W0221
        self.message_log('Start Init section')
        tcm = self.get_trading_capability_manager()
        self.f_currency = self.get_first_currency()
        self.s_currency = self.get_second_currency()
        self.tlg_header = '{}, {}/{}. '.format(EXCHANGE[ID_EXCHANGE], self.f_currency, self.s_currency)
        self.message_log(f"{self.tlg_header}", color=Style.B_WHITE)
        self.status_time = time.time()
        self.cycle_time = datetime.utcnow()
        self.start_after_shift = True
        self.over_price = OVER_PRICE
        self.order_q = ORDER_Q
        self.martin = (MARTIN + 100) / 100
        if not check_funds:
            self.first_run = False
        if GRID_ONLY:
            self.message_log('Mode for buy/sell asset by grid orders placement ON', color=Style.B_WHITE)
        if Decimal('0.0') > PROFIT_REVERSE > Decimal('0.75'):
            self.message_log("Incorrect value for PROFIT_REVERSE", log_level=LogLevel.ERROR)
            if STANDALONE:
                os._exit(1)
        # Calculate round float multiplier
        self.round_base = ROUND_BASE or str(tcm.round_amount(1.0123456789, RoundingType.FLOOR))
        self.round_quote = ROUND_QUOTE or str(tcm.round_price(1.0123456789, RoundingType.FLOOR))
        print(f"Round pattern, for base: {self.round_base}, quote: {self.round_quote}")
        last_price = float2decimal(self.get_buffered_ticker().last_price)
        if last_price:
            print('Last ticker price: ', last_price)
            self.avg_rate = last_price
            df = self.get_buffered_funds().get(self.f_currency, 0)
            df = float2decimal(df.available) if df else Decimal('0.0')
            if USE_ALL_FIRST_FUND and df and self.cycle_buy:
                self.message_log('Check USE_ALL_FIRST_FUND parameter. You may have loss on Reverse cycle',
                                 color=Style.B_WHITE)
            if self.cycle_buy:
                ds = self.get_buffered_funds().get(self.s_currency, 0)
                ds = float2decimal(ds.available) if ds else Decimal('0.0')
                if check_funds and self.deposit_second > ds:
                    self.message_log('Not enough second coin for Buy cycle!', color=Style.B_RED)
                    if STANDALONE:
                        os._exit(1)
                first_order_vlm = self.deposit_second * 1 * (1 - self.martin) / (1 - self.martin**ORDER_Q)
                first_order_vlm /= last_price
            else:
                if USE_ALL_FIRST_FUND:
                    self.deposit_first = df
                else:
                    if check_funds and self.deposit_first > df:
                        self.message_log('Not enough first coin for Sell cycle!', color=Style.B_RED)
                        if STANDALONE:
                            os._exit(1)
                first_order_vlm = self.deposit_first * 1 * (1 - self.martin) / (1 - pow(self.martin, ORDER_Q))
            if self.cycle_buy and first_order_vlm < float2decimal(tcm.get_min_buy_amount(float(last_price))):
                self.message_log(f"Total deposit {AMOUNT_SECOND}{self.s_currency}"
                                 f" not enough for min amount for {ORDER_Q} orders.", color=Style.B_RED)
            elif not self.cycle_buy and first_order_vlm < float2decimal(tcm.get_min_sell_amount(float(last_price))):
                self.message_log(f"Total deposit {self.deposit_first}{self.f_currency}"
                                 f" not enough for min amount for {ORDER_Q} orders.", color=Style.B_RED)
            buy_amount = tcm.get_min_buy_amount(float(last_price))
            sell_amount = tcm.get_min_sell_amount(float(last_price))
            print(f"buy_amount: {buy_amount}, sell_amount: {sell_amount}")
        else:
            print('Actual price not received, initialization checks skipped')
        # self.message_log('End Init section')

    @staticmethod
    def get_strategy_config() -> StrategyConfig:
        print('Get config')
        s = StrategyConfig()
        s.required_data_updates = {StrategyConfig.ORDER_BOOK,
                                   StrategyConfig.FUNDS,
                                   StrategyConfig.TICKER}
        s.normalize_exchange_buy_amounts = True
        return s

    def save_strategy_state(self) -> Dict[str, str]:
        # region ReportStatus
        # Get command from Telegram
        command = None
        if self.connection_analytic:
            cursor_analytic = self.connection_analytic.cursor()
            bot_id = self.tlg_header.split('.')[0]
            cursor_analytic.execute('SELECT max(message_id), text_in, bot_id\
                                    FROM t_control WHERE bot_id=:bot_id', {'bot_id': bot_id})
            row = cursor_analytic.fetchone()
            if row[0]:
                # Analyse and execute received command
                command = row[1]
                if command != 'status':
                    self.command = command
                    command = None
                # Remove applied command from .db
                cursor_analytic.execute('UPDATE t_control SET apply = 1 WHERE message_id=:message_id',
                                        {'message_id': row[0]})
                self.connection_analytic.commit()
            # self.message_log(f"save_strategy_state.command: {self.command}", log_level=LogLevel.DEBUG)
        if command or ((time.time() - self.status_time) / 60 > STATUS_DELAY and self.command != 'end'):
            # Report current status
            last_price = self.get_buffered_ticker().last_price
            if self.cycle_time:
                ct = str(datetime.utcnow() - self.cycle_time).rsplit('.')[0]
            else:
                self.message_log("save_strategy_state: cycle_time is None!", log_level=LogLevel.DEBUG)
                ct = str(datetime.utcnow()).rsplit('.')[0]
            if self.grid_hold:
                funds = self.get_buffered_funds()
                if self.cycle_buy:
                    fund = funds.get(self.s_currency, 0)
                    fund = fund.available if fund else 0
                    currency = self.s_currency
                else:
                    fund = funds.get(self.f_currency, 0)
                    fund = fund.available if fund else 0
                    currency = self.f_currency
                time_diff = None
                if self.grid_hold.get('timestamp'):
                    time_diff = int(time.time() - self.grid_hold['timestamp'])
                self.message_log(f"Exist unreleased grid orders for\n"
                                 f"{'Buy' if self.cycle_buy else 'Sell'} cycle with"
                                 f" {self.grid_hold['depo']}{currency} depo.\n"
                                 f"Available funds is {fund} {currency}\n"
                                 f"Last ticker price: {last_price}\n"
                                 f"From start {ct}\n"
                                 f"Time difference: {time_diff} sec", tlg=True)
            else:
                orders = self.get_buffered_open_orders()
                order_buy = len([i for i in orders if i.buy is True])
                order_sell = len([i for i in orders if i.buy is False])
                order_hold = len(self.orders_hold)
                sum_profit = self.round_truncate(self.sum_profit_first * self.avg_rate + self.sum_profit_second,
                                                 base=False)
                self.message_log(f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                                 f"For all cycles profit:\n"
                                 f"First: {self.sum_profit_first}\n"
                                 f"Second: {self.sum_profit_second}\n"
                                 f"Summary: {sum_profit}\n"
                                 f"*   ***   ***   ***   *\n"
                                 f"{'Buy' if self.cycle_buy else 'Sell'}{' Reverse' if self.reverse else ''}"
                                 f"{' Hold reverse' if self.reverse_hold else ''}"
                                 f" {'grid only' if GRID_ONLY else 'cycle'} with {order_buy} buy"
                                 f" and {order_sell} sell active orders.\n"
                                 f"{order_hold if order_hold else 'No'} hold grid orders\n"
                                 f"Over price: {self.over_price:.2f}%\n"
                                 f"Last ticker price: {last_price}\n"
                                 f"ver: {HEAD_VERSION}+{__version__}+{msb_ver}\n"
                                 f"From start {ct}\n"
                                 f"{'-   ***   ***   ***   -' if self.command == 'stop' else ''}\n"
                                 f"{'Waiting for end of cycle for manual action' if self.command == 'stop' else ''}",
                                 tlg=True)
        # endregion
        # region ProcessingEvent
        if not STANDALONE and EXTRA_CHECK_ORDER_STATE:
            self.heartbeat_counter += 1
            if self.heartbeat_counter >= 5:
                self.heartbeat_counter = 0
                self.check_order_status()
        if self.wait_refunding_for_start or self.tp_order_hold or self.grid_hold:
            self.get_buffered_funds()
        if self.tp_error:
            self.tp_error = False
            self.place_profit_order()
        if self.reverse_hold:
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
                self.part_amount_first = Decimal('0')
                self.part_amount_second = Decimal('0')
                self.tp_part_amount_first = Decimal('0')
                self.tp_part_amount_second = Decimal('0')
                self.message_log('Release Hold reverse cycle', color=Style.B_WHITE)
                self.start()
        if time.time() - self.grid_hold.get('timestamp', time.time()) > SHIFT_GRID_DELAY:
            self.grid_hold['timestamp'] = None
            self.message_log("Try release hold grid", tlg=True)
            buy_side = self.grid_hold['buy_side']
            depo = self.grid_hold['depo']
            #
            funds = self.get_buffered_funds()
            ff = funds.get(self.f_currency, 0)
            ff = self.round_truncate(float2decimal(ff.available) if ff else Decimal('0.0'), base=True)
            fs = funds.get(self.s_currency, 0)
            fs = self.round_truncate(float2decimal(fs.available) if fs else Decimal('0.0'), base=False)
            #
            if buy_side:
                diff_s = self.deposit_second - fs
                diff_f = diff_s / self.avg_rate
                go_trade = bool(ff >= diff_f)
            else:
                diff_f = self.deposit_first - ff
                diff_s = diff_f * self.avg_rate
                go_trade = bool(fs >= diff_s)
            #
            self.message_log(f"go_trade: {go_trade}, ff: {ff:f}, fs: {fs:f}, avg_rate: {self.avg_rate},"
                             f" diff_f: {diff_f:f}, diff_s: {diff_s:f}", log_level=LogLevel.DEBUG)
            if go_trade:
                self.message_log(f"Release grid hold: necessary {depo}, exist {fs if buy_side else ff}\n"
                                 f"Difference first: {diff_f}, second: {diff_s}")
                self.sum_amount_first += diff_f
                self.sum_amount_second += diff_s
                self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                                 f" Sum_amount_second: {self.sum_amount_second}",
                                 log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                depo = fs if buy_side else ff
                self.message_log(f"New depo is {depo}")
                # Check min amount for placing TP
                if self.check_min_amount_for_tp():
                    self.tp_hold_additional = True
                    self.place_grid(buy_side, depo, self.reverse_target_amount)
        # endregion
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
                'part_amount_first': json.dumps(self.part_amount_first),
                'part_amount_second': json.dumps(self.part_amount_second),
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
                'tp_init': json.dumps(str(self.tp_init)),
                'tp_order_id': json.dumps(self.tp_order_id),
                'tp_part_amount_first': json.dumps(self.tp_part_amount_first),
                'tp_part_amount_second': json.dumps(self.tp_part_amount_second),
                'tp_target': json.dumps(self.tp_target),
                'tp_order': json.dumps(str(self.tp_order)),
                'tp_wait_id': json.dumps(self.tp_wait_id)}

    def restore_strategy_state(self, strategy_state: Dict[str, str] = None) -> None:
        if strategy_state:
            # Restore from file if lose state only
            self.message_log("restore_strategy_state from saved state:", log_level=LogLevel.DEBUG)
            self.message_log("\n".join(f"{k}\t{v}" for k, v in strategy_state.items()), log_level=LogLevel.DEBUG)
            #
            self.command = json.loads(strategy_state.get('command'))
            self.cycle_buy = json.loads(strategy_state.get('cycle_buy'))
            self.cycle_buy_count = json.loads(strategy_state.get('cycle_buy_count'))
            self.cycle_sell_count = json.loads(strategy_state.get('cycle_sell_count'))
            self.cycle_time = datetime.strptime(json.loads(strategy_state.get('cycle_time')), '%Y-%m-%d %H:%M:%S.%f')
            self.cycle_time_reverse = json.loads(strategy_state.get('cycle_time_reverse'))
            if self.cycle_time_reverse:
                self.cycle_time_reverse = datetime.strptime(self.cycle_time_reverse, '%Y-%m-%d %H:%M:%S.%f')
            else:
                self.cycle_time_reverse = None
            self.deposit_first = float2decimal(json.loads(strategy_state.get('deposit_first')))
            self.deposit_second = float2decimal(json.loads(strategy_state.get('deposit_second')))
            self.last_shift_time = json.loads(strategy_state.get('last_shift_time'))
            self.martin = float2decimal(json.loads(strategy_state.get('martin')))
            self.order_q = json.loads(strategy_state.get('order_q'))
            self.orders_grid.restore(json.loads(strategy_state.get('orders')))
            self.orders_hold.restore(json.loads(strategy_state.get('orders_hold')))
            self.orders_save.restore(json.loads(strategy_state.get('orders_save')))
            self.over_price = json.loads(strategy_state.get('over_price'))
            self.part_amount_first = float2decimal(json.loads(strategy_state.get('part_amount_first')))
            self.part_amount_second = float2decimal(json.loads(strategy_state.get('part_amount_second')))
            self.initial_first = float2decimal(json.loads(strategy_state.get('initial_first')))
            self.initial_second = float2decimal(json.loads(strategy_state.get('initial_second')))
            self.initial_reverse_first = float2decimal(json.loads(strategy_state.get('initial_reverse_first')))
            self.initial_reverse_second = float2decimal(json.loads(strategy_state.get('initial_reverse_second')))
            self.profit_first = float2decimal(json.loads(strategy_state.get('profit_first')))
            self.profit_second = float2decimal(json.loads(strategy_state.get('profit_second')))
            self.reverse = json.loads(strategy_state.get('reverse'))
            self.reverse_hold = json.loads(strategy_state.get('reverse_hold'))
            self.reverse_init_amount = float2decimal(json.loads(strategy_state.get('reverse_init_amount')))
            self.reverse_price = json.loads(strategy_state.get('reverse_price'))
            self.reverse_target_amount = json.loads(strategy_state.get('reverse_target_amount'))
            self.shift_grid_threshold = json.loads(strategy_state.get('shift_grid_threshold'))
            self.status_time = json.loads(strategy_state.get('status_time'))
            self.sum_amount_first = float2decimal(json.loads(strategy_state.get('sum_amount_first')))
            self.sum_amount_second = float2decimal(json.loads(strategy_state.get('sum_amount_second')))
            self.sum_profit_first = float2decimal(json.loads(strategy_state.get('sum_profit_first')))
            self.sum_profit_second = float2decimal(json.loads(strategy_state.get('sum_profit_second')))
            self.tp_amount = float2decimal(json.loads(strategy_state.get('tp_amount')))
            self.tp_init = eval(json.loads(strategy_state.get('tp_init')))
            self.tp_order_id = json.loads(strategy_state.get('tp_order_id'))
            self.tp_part_amount_first = float2decimal(json.loads(strategy_state.get('tp_part_amount_first')))
            self.tp_part_amount_second = float2decimal(json.loads(strategy_state.get('tp_part_amount_second')))
            self.tp_target = float2decimal(json.loads(strategy_state.get('tp_target')))
            self.tp_order = eval(json.loads(strategy_state.get('tp_order'))) if strategy_state.get('tp_order') else ()
            self.tp_wait_id = json.loads(strategy_state.get('tp_wait_id')) if strategy_state.get('tp_wait_id') else None
        # Variants are processed when the actual order is equal to or less than it should be
        # Exotic when drop during placed grid or unconfirmed TP left for later
        self.start_process()
        open_orders = self.get_buffered_open_orders(True)  # lgtm [py/call/wrong-arguments]
        tp_order = None
        # Separate TP order
        if self.tp_order_id:
            for i, o in enumerate(open_orders):
                if o.id == self.tp_order_id:
                    tp_order = open_orders[i]
                    del open_orders[i]  # skipcq: PYL-E1138
                    break
        # Possible strategy states in compare with saved one
        grid_orders_len = len(self.orders_grid)
        open_orders_len = len(open_orders)
        grid_no_change = grid_orders_len == open_orders_len  # Grid No change
        grid_less = grid_orders_len > open_orders_len > 0
        grid_hold = open_orders_len == 0 and self.orders_hold
        grid_more = grid_orders_len < open_orders_len  # Grid more, some order(s) was placed
        grid_filled = grid_orders_len > 0 and open_orders_len == 0 and not self.orders_hold  # Grid was complete
        tp_no_change = (tp_order and self.tp_order_id) or (not tp_order and not self.tp_order_id)
        tp_placed = tp_order and not self.tp_order_id
        tp_filled = not tp_order and self.tp_order_id
        no_orders = grid_orders_len == 0 and not self.tp_order_id
        #
        self.avg_rate = float2decimal(self.get_buffered_ticker().last_price)
        #
        if grid_no_change and tp_no_change:
            if grid_hold:
                self.message_log("Restore, no grid orders, place from hold now", tlg=True)
                self.place_grid_part()
            elif no_orders:
                self.restart = True
                self.message_log("Restore, no orders, restart", tlg=True)
                self.start()
            elif not self.tp_order_id and self.check_min_amount_for_tp():
                self.message_log("Restore, replace TP", tlg=True)
                self.place_profit_order()
            else:
                self.message_log("Restore, No difference, go work", tlg=True)

        elif grid_filled and tp_filled:
            self.message_log("Restore, all grid orders and TP was filled", tlg=True)
            # Get actual parameter of filled tp order
            market_order = self.get_buffered_completed_trades(True)
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for o in market_order:
                if o.order_id == self.tp_order_id:
                    amount_first += float2decimal(o.amount)
                    amount_second += float2decimal(o.amount) * float2decimal(o.price)
            self.tp_was_filled = (amount_first, amount_second, True,)
            self.tp_order_id = None
            self.tp_order = ()
            self.message_log(f"restore_strategy_state.was_filled_tp: {self.tp_was_filled}", log_level=LogLevel.DEBUG)
            # Calculate sum trade amount for both currency
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for i in self.orders_grid:
                amount_first += i['amount']
                amount_second += i['amount'] * i['price']
                print(f"id={i['id']}, first: {i['amount']}, price: {i['price']}")
            print(f"Total grid amount first: {amount_first}, second: {amount_second}")
            # Clear list of grid order
            self.orders_grid.orders_list.clear()
            self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)

        elif grid_filled and tp_no_change:
            self.message_log('Restore, No grid orders -> Reverse', tlg=True)
            # Admit that missing orders were executed on conditions no worse than those saved
            # Calculate sum trade amount for both currency
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for i in self.orders_grid:
                amount_first += i['amount']
                amount_second += i['amount'] * i['price']
                print(f"id={i['id']}, first: {i['amount']}, price: {i['price']}")
            print(f"Total amount first: {amount_first}, second: {amount_second}")
            # Clear list of grid order
            self.orders_grid.orders_list.clear()
            self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)

        elif grid_less and tp_filled:
            self.message_log("Restore, some grid orders and TP was filled", tlg=True)
            # Get actual parameter of filled tp order
            market_order = self.get_buffered_completed_trades(True)
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for o in market_order:
                if o.order_id == self.tp_order_id:
                    amount_first += float2decimal(o.amount)
                    amount_second += float2decimal(o.amount) * float2decimal(o.price)
                    print(f"order_id={o.order_id}, first: {o.amount}, price: {o.price}")
            self.tp_was_filled = (amount_first, amount_second, True,)
            self.tp_order_id = None
            self.tp_order = ()
            self.message_log(f"restore_strategy_state.was_filled_tp: {self.tp_was_filled}", log_level=LogLevel.DEBUG)
            # Calculate sum trade amount for both currency
            exch_orders_id = []
            save_orders_id = []
            for i in open_orders:
                exch_orders_id.append(i.id)
            for i in self.orders_grid:
                save_orders_id.append(i.get('id'))
            print(f"restore_strategy_state.exch_orders_id: {exch_orders_id}")
            print(f"restore_strategy_state.save_orders_id: {save_orders_id}")
            diff_id = list(set(save_orders_id).difference(exch_orders_id))
            print(f"Executed order id is: {diff_id}")
            # Calculate sum trade amount for both currency
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for i in self.orders_grid:
                if i['id'] in diff_id:
                    amount_first += i['amount']
                    amount_second += i['amount'] * i['price']
                    print(f"id={i['id']}, first: {i['amount']}, price: {i['price']}")
            self.message_log(f"Total amount first: {amount_first:f}, second: {amount_second:f}", color=Style.B_WHITE)
            # Remove from list of grid order
            for i in diff_id:
                self.orders_grid.remove(i)
            # Calculate trade amount with Fee
            amount_first_fee, amount_second_fee = self.fee_for_grid(amount_first, amount_second)
            # Calculate cycle sum trading for both currency
            self.sum_amount_first += amount_first_fee
            self.sum_amount_second += amount_second_fee
            if open_orders_len == 0 and self.orders_hold:
                self.place_grid_part()
            self.after_filled_tp(one_else_grid=True)

        elif grid_less:
            self.message_log("Restore, Less grid orders -> replace tp order", tlg=True)
            exch_orders_id = []
            save_orders_id = []
            for i in open_orders:
                exch_orders_id.append(i.id)
            for i in self.orders_grid:
                save_orders_id.append(i.get('id'))
            print(f"restore_strategy_state.exch_orders_id: {exch_orders_id}")
            print(f"restore_strategy_state.save_orders_id: {save_orders_id}")
            diff_id = list(set(save_orders_id).difference(exch_orders_id))
            print(f"Executed order id is: {diff_id}")
            # Calculate sum trade amount for both currency
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for i in self.orders_grid:
                if i['id'] in diff_id:
                    amount_first += i['amount']
                    amount_second += i['amount'] * i['price']
                    print(f"id={i['id']}, first: {i['amount']}, price: {i['price']}")
            self.message_log(f"Total amount first: {amount_first:f}, second: {amount_second:f}", color=Style.B_WHITE)
            # Remove from list of grid order
            for i in diff_id:
                self.orders_grid.remove(i)
            self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)

        elif tp_filled:
            self.message_log('Restore, TP order was filled -> Restart', tlg=True)
            # Get actual parameter of filled tp order
            market_order = self.get_buffered_completed_trades(True)
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for o in market_order:
                if o.order_id == self.tp_order_id:
                    amount_first += float2decimal(o.amount)
                    amount_second += float2decimal(o.amount) * float2decimal(o.price)
                    print(f"order_id={o.order_id}, first: {o.amount}, price: {o.price}")
            self.tp_was_filled = (amount_first, amount_second, True,)
            self.tp_order_id = None
            self.tp_order = ()
            self.grid_remove = True
            self.cancel_grid()

        elif grid_more and self.orders_init:
            self.message_log('Restore, was placed some grid order(s)', tlg=True)

        elif tp_placed:
            self.message_log('Restore, was placed take profit order(s)', tlg=True)

        else:
            self.message_log('Restore, some else. Need investigations.', tlg=True)
        # self.unsuspend()

    def start(self) -> None:
        self.message_log('Start')
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
                self.cancel_order(self.tp_order_id)
            return
        if self.tp_wait_id:
            # Wait tp order and cancel in on_cancel_order_success and restart
            self.tp_cancel = True
            return
        funds = self.get_buffered_funds()
        ff = funds.get(self.f_currency, 0)
        ff = float2decimal(ff.total_for_currency) if ff else Decimal('0.0')
        fs = funds.get(self.s_currency, 0)
        fs = float2decimal(fs.total_for_currency) if fs else Decimal('0.0')
        # Save initial funds and cycle statistics to .db for external analytics
        if self.first_run:
            self.start_process()
            if self.reverse:
                self.initial_reverse_first = self.round_truncate(ff, base=True)
                self.initial_reverse_second = self.round_truncate(fs, base=False)
            else:
                self.initial_first = self.round_truncate(ff, base=True)
                self.initial_second = self.round_truncate(fs, base=False)
        elif self.restart and not GRID_ONLY:
            if self.reverse:
                delta_f = ff - self.initial_reverse_first
                delta_s = fs - self.initial_reverse_second
            else:
                delta_f = ff - self.initial_first
                delta_s = fs - self.initial_second
            delta = delta_f * self.avg_rate + delta_s
            self.message_log(f"Operational difference from initial funds: {delta}")
            go_trade = True
            if delta < 0:
                tcm = self.get_trading_capability_manager()
                # Set maximum loss at 10% from minimum lot size, if was a rounding error
                min_delta = float2decimal(0.1 * tcm.get_min_buy_amount(float(self.avg_rate))) * self.avg_rate
                if delta.copy_abs() > min_delta:
                    go_trade = False
            if self.wait_refunding_for_start or go_trade:
                self.wait_refunding_for_start = False
                if self.reverse:
                    self.initial_reverse_first = self.round_truncate(ff, base=True, _rounding=ROUND_FLOOR)
                    self.initial_reverse_second = self.round_truncate(fs, base=False, _rounding=ROUND_FLOOR)
                    ff = self.initial_first
                    fs = self.initial_second
                    pf = PROFIT_REVERSE * self.profit_first / (1 - PROFIT_REVERSE)
                    ps = PROFIT_REVERSE * self.profit_second / (1 - PROFIT_REVERSE)
                else:
                    self.initial_first = self.round_truncate(ff, base=True, _rounding=ROUND_FLOOR)
                    self.initial_second = self.round_truncate(fs, base=False, _rounding=ROUND_FLOOR)
                    pf = self.profit_first
                    ps = self.profit_second
                if self.cycle_buy:
                    df = Decimal('0')
                    ds = self.deposit_second - self.profit_second
                else:
                    df = self.deposit_first - self.profit_first
                    ds = Decimal('0')
                ct = datetime.utcnow() - self.cycle_time
                ct = ct.total_seconds()
                data_to_db = {'f_currency': self.f_currency,
                              's_currency': self.s_currency,
                              'f_funds': ff,
                              's_funds': fs,
                              'avg_rate': self.avg_rate,
                              'cycle_buy': self.cycle_buy,
                              'f_depo': df,
                              's_depo': ds,
                              'f_profit': pf,
                              's_profit': ps,
                              'order_q': self.order_q,
                              'over_price': self.over_price,
                              'cycle_time': ct}
                if self.queue_to_db:
                    print('Save data to .db')
                    self.queue_to_db.put(data_to_db)
            else:
                self.wait_refunding_for_start = True
                self.message_log(f"Wait refunding for start, having now: first: {ff}, second: {fs}")
                return
        self.avg_rate = float2decimal(self.get_buffered_ticker().last_price)
        if not self.first_run and not self.start_after_shift and not self.reverse and not GRID_ONLY:
            self.message_log(f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                             f"For all cycles profit:\n"
                             f"First: {self.sum_profit_first}\n"
                             f"Second: {self.sum_profit_second}\n"
                             f"Summary: {self.sum_profit_first * self.avg_rate + self.sum_profit_second:f}")
        mem = psutil.virtual_memory().percent
        if mem > 80:
            self.message_log(f"For {VPS_NAME} critical memory availability, end", tlg=True)
            self.command = 'end'
        elif mem > 70:
            self.message_log(f"For {VPS_NAME} low memory availability, stop after end of cycle", tlg=True)
            self.command = 'stop'
        if self.command == 'end' or (self.command == 'stop' and
                                     (not self.reverse or (self.reverse and REVERSE_STOP))):
            self.message_log('Stop, waiting manual action', tlg=True)
        else:
            n = gc.collect(generation=2)
            print('Number of unreachable objects collected by GC:', n)
            self.message_log(f"Initial first: {self.initial_reverse_first if self.reverse else self.initial_first},"
                             f" second: {self.initial_reverse_second if self.reverse else self.initial_second}",
                             color=Style.B_WHITE)
            self.restart = None
            # Init variable
            self.profit_first = Decimal('0')
            self.profit_second = Decimal('0')
            self.cycle_time = datetime.utcnow()
            self.over_price = OVER_PRICE
            self.order_q = ORDER_Q
            if self.cycle_buy:
                amount = self.deposit_second
                if not self.start_after_shift or self.first_run:
                    self.message_log(f"Start Buy{' Reverse' if self.reverse else ''}"
                                     f" {'asset' if GRID_ONLY else 'cycle'} with "
                                     f"{amount:f} {self.s_currency} depo", tlg=True)
            else:
                if USE_ALL_FIRST_FUND and (self.reverse or GRID_ONLY):
                    ff = funds.get(self.f_currency, 0)
                    fund = float2decimal(ff.available) if ff else Decimal('0.0')
                    if fund > self.deposit_first:
                        self.deposit_first = fund
                        self.message_log('Use all available fund for first currency')
                        self.deposit_first = self.round_truncate(self.deposit_first, base=True)
                amount = self.deposit_first
                if not self.start_after_shift or self.first_run:
                    self.message_log(f"Start Sell{' Reverse' if self.reverse else ''}"
                                     f" {'asset' if GRID_ONLY else 'cycle'} with "
                                     f"{amount:f} {self.f_currency} depo", tlg=True)
            if self.reverse:
                self.message_log(f"For Reverse cycle target return amount: {self.reverse_target_amount}",
                                 color=Style.B_WHITE)
            self.start_after_shift = False
            self.first_run = False
            self.debug_output()
            self.place_grid(self.cycle_buy, amount, self.reverse_target_amount)

    def stop(self) -> None:
        self.message_log('Stop')
        self.queue_to_db.put({'stop_signal': True})
        self.queue_to_tlg.put('stop_signal_QWE#@!')
        self.connection_analytic.commit()
        self.connection_analytic.close()
        self.connection_analytic = None

    def suspend(self) -> None:
        print('Suspend')
        self.queue_to_db.put({'stop_signal': True})
        self.queue_to_tlg.put('stop_signal_QWE#@!')
        self.connection_analytic.commit()
        self.connection_analytic.close()
        self.connection_analytic = None

    def unsuspend(self) -> None:
        print('Unsuspend')
        self.start_process()

    ##############################################################
    # strategy function
    ##############################################################

    def place_grid(self,
                   buy_side: bool,
                   depo: Decimal,
                   reverse_target_amount: float,
                   allow_grid_shift: bool = True) -> None:
        self.message_log(f"place_grid: buy_side:{buy_side}, depo: {depo},"
                         f" reverse_target_amount: {reverse_target_amount},"
                         f" allow_grid_shift: {allow_grid_shift}", log_level=LogLevel.DEBUG)
        self.grid_hold.clear()
        self.last_shift_time = None
        tcm = self.get_trading_capability_manager()
        if buy_side:
            max_bid_price = self.get_buffered_order_book().bids[0].price
            base_price = max_bid_price - PRICE_SHIFT * max_bid_price / 100
            min_amount = tcm.get_min_buy_amount(base_price)
        else:
            min_ask_price = self.get_buffered_order_book().asks[0].price
            base_price = min_ask_price + PRICE_SHIFT * min_ask_price / 100
            min_amount = tcm.get_min_sell_amount(base_price)
        # print(f"place_grid.base_price: {base_price}")
        min_delta = tcm.get_minimal_price_change(base_price)
        if ADAPTIVE_TRADE_CONDITION or self.reverse:
            try:
                self.set_trade_conditions(buy_side, float(depo), base_price, reverse_target_amount,
                                          min_amount, min_delta)
            except Exception as ex:
                self.message_log(f"Do not set trade conditions: {ex}", log_level=LogLevel.ERROR, color=Style.B_RED)
                self.over_price = OVER_PRICE
                self.order_q = ORDER_Q
        self.message_log(f"For{' Reverse' if self.reverse else ''} {'Buy' if buy_side else 'Sell'}"
                         f" cycle set {self.order_q} orders for {self.over_price:.2f}% over price", tlg=False)
        # Decimal zone
        base_price_dec = float2decimal(base_price)
        min_delta_dec = float2decimal(min_delta)
        delta_price = self.over_price * base_price_dec / (100 * (self.order_q - 1))
        funds = self.get_buffered_funds()
        price_prev = base_price_dec
        if buy_side:
            fund = funds.get(self.s_currency, 0)
            fund = float2decimal(fund.available) if fund else Decimal('0.0')
            currency = self.s_currency
        else:
            fund = funds.get(self.f_currency, 0)
            fund = float2decimal(fund.available) if fund else Decimal('0.0')
            currency = self.f_currency
        if depo <= fund:
            for i in range(self.order_q):
                if LINEAR_GRID_K >= 0:
                    price_k = float2decimal(1 - math.log(self.order_q - i, self.order_q + LINEAR_GRID_K))
                else:
                    price_k = 1
                if buy_side:
                    price = base_price_dec - i * delta_price * price_k
                else:
                    price = base_price_dec + i * delta_price * price_k
                price = float2decimal(tcm.round_price(float(price), RoundingType.ROUND))
                if buy_side:
                    if i and price_prev - price < min_delta_dec:
                        price = price_prev - min_delta_dec
                else:
                    if i and price - price_prev < min_delta_dec:
                        price = price_prev + min_delta_dec
                price_prev = price
                # print(f"place_grid.round_price: {price}")
                amount = depo * self.martin**i * (1 - self.martin) / (1 - self.martin**self.order_q)
                if buy_side:
                    amount /= price
                amount = self.round_truncate(amount, base=True)
                # create order for grid
                if i < GRID_MAX_COUNT:
                    waiting_order_id = self.place_limit_order(buy_side, float(amount), float(price))
                    self.orders_init.append(waiting_order_id, buy_side, amount, price)
                else:
                    self.orders_hold.append(i, buy_side, amount, price)
            if not GRID_ONLY and allow_grid_shift:
                if buy_side:
                    self.shift_grid_threshold = base_price + 2 * PRICE_SHIFT * base_price / 100
                else:
                    self.shift_grid_threshold = base_price - 2 * PRICE_SHIFT * base_price / 100
                self.message_log(f"Shift grid threshold: {self.shift_grid_threshold:.2f}")
        else:
            self.grid_hold = {'buy_side': buy_side,
                              'depo': depo,
                              'timestamp': time.time()}
            self.message_log(f"Hold grid for {'Buy' if buy_side else 'Sell'} cycle with {depo} {currency} depo."
                             f" Available funds is {fund} {currency}", tlg=False)
        if self.tp_hold_additional:
            self.message_log("Replace take profit order after place additional grid orders", tlg=True)
            self.tp_hold_additional = False
            self.place_profit_order()

    def place_profit_order(self, by_market: bool = False) -> None:
        # TODO Check for min amount
        if not GRID_ONLY:
            self.message_log(f"place_profit_order: by_market: {by_market}", log_level=LogLevel.DEBUG)
            self.tp_order_hold.clear()
            if self.tp_wait_id or self.cancel_order_id or self.tp_was_filled:
                # Waiting confirm or cancel old or processing ending and replace it
                self.tp_hold = True
                self.message_log('Waiting finished TP order for replace', color=Style.B_WHITE)
            elif self.tp_order_id:
                # Cancel take profit order, place new
                self.tp_hold = True
                self.cancel_order_id = self.tp_order_id
                self.cancel_order(self.tp_order_id)
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
                    fund = funds.get(self.s_currency, 0)
                    fund = float2decimal(fund.available) if fund else Decimal('0.0')
                else:
                    fund = funds.get(self.f_currency, 0)
                    fund = float2decimal(fund.available) if fund else Decimal('0.0')
                if buy_side and amount * price > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side,
                                          'amount': amount * price}
                    self.message_log(f"Hold take profit order for Buy {amount} {self.f_currency} by {price},"
                                     f" wait {amount * price} {self.s_currency}, exist: {fund}")
                elif not buy_side and amount > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side, 'amount': amount}
                    self.message_log(f"Hold take profit order for Sell {amount} {self.f_currency}"
                                     f" by {price}, exist {fund}")
                else:
                    # Create take profit order
                    self.message_log(f"Create {'Buy' if buy_side else 'Sell'} take profit order,"
                                     f" vlm: {amount}, price: {price}, profit: {profit}%")
                    self.tp_target = target
                    _amount = float(amount)
                    _price = float(price)
                    if not STANDALONE:
                        tcm = self.get_trading_capability_manager()
                        if not tcm.is_limit_order_valid(buy_side, _amount, _price):
                            _amount = tcm.round_amount(_amount, RoundingType.FLOOR)
                            if buy_side:
                                _price = tcm.round_price(_price, RoundingType.FLOOR)
                            else:
                                _price = tcm.round_price(_price, RoundingType.CEIL)
                            self.message_log(f"Rounded amount: {_amount}, price: {_price}")
                    self.tp_order = (buy_side, _amount, _price)
                    self.tp_wait_id = self.place_limit_order(buy_side, _amount, _price)

    def message_log(self, msg: str, log_level=LogLevel.INFO, tlg: bool = False, color=Style.WHITE) -> None:
        if tlg and color == Style.WHITE:
            color = Style.B_WHITE
        if log_level in (LogLevel.ERROR, LogLevel.CRITICAL):
            tlg = True
            color = Style.B_RED
        color = color if STANDALONE else 0
        color_msg = color+msg+Style.RESET if color else msg
        if log_level not in LOG_LEVEL_NO_PRINT:
            print(f"{datetime.now().strftime('%d/%m %H:%M:%S')} {color_msg}")
        write_log(log_level, msg)
        msg = self.tlg_header + msg
        if tlg and self.queue_to_tlg:
            self.status_time = time.time()
            self.queue_to_tlg.put(msg)

    def bollinger_band(self, candle_size_in_minutes: int, number_of_candles: int) -> Dict[str, float]:
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
        self.message_log(f"bollinger_band: tbb={tbb}, bbb={bbb}")
        return {'tbb': tbb, 'bbb': bbb}

    def set_trade_conditions(self,
                             buy_side: bool,
                             depo: float,
                             base_price: float,
                             reverse_target_amount: float,
                             amount_min: float,
                             delta_min: float) -> None:
        self.message_log(f"set_trade_conditions: buy_side: {buy_side}, depo: {depo}, base_price: {base_price},"
                         f" reverse_target_amount: {reverse_target_amount}, amount_min: {amount_min},"
                         f" delta_min: {delta_min}", LogLevel.DEBUG)
        if buy_side:
            depo /= base_price
        over_price_min = max(100 * delta_min * ORDER_Q / base_price, 0.01 * ORDER_Q)
        # print('over_price_min: {}'.format(over_price_min))
        if self.reverse:
            over_price = self.calc_over_price(buy_side, depo, base_price, reverse_target_amount)
        else:
            bb = self.bollinger_band(BB_CANDLE_SIZE_IN_MINUTES, BB_NUMBER_OF_CANDLES)
            if buy_side:
                bbb = bb.get('bbb')
                over_price = 100*(base_price - bbb) / base_price
            else:
                tbb = bb.get('tbb')
                over_price = 100 * (tbb - base_price) / base_price
        self.over_price = float2decimal(over_price if over_price >= over_price_min else
                                        OVER_PRICE if over_price <= 0 else over_price_min)
        # Adapt grid orders quantity for current over price
        order_q = int(float(self.over_price) * ORDER_Q / float(OVER_PRICE))
        q_max = int(math.log(1 - depo * (1 - float(self.martin)) / (amount_min * 1.5), float(self.martin)))
        while True:
            delta_price = float(self.over_price) * base_price / (100 * (q_max - 1))
            if LINEAR_GRID_K >= 0:
                price_k = 1 - math.log(q_max - 1, q_max + LINEAR_GRID_K)
            else:
                price_k = 1
            delta = delta_price * price_k
            if delta > delta_min or q_max <= ORDER_Q:
                break
            q_max -= 1
        self.order_q = q_max if order_q > q_max else order_q if order_q >= ORDER_Q else ORDER_Q
        # Correction over_price after change quantity of order
        if self.reverse:
            over_price = self.calc_over_price(buy_side, depo, base_price, reverse_target_amount, exactly=True)
            self.over_price = float2decimal(over_price if over_price >= over_price_min else over_price_min)

    def set_profit(self) -> Decimal:
        self.message_log("set_profit", LogLevel.DEBUG)
        last_price = None
        tbb = None
        bbb = None
        try:
            bb = self.bollinger_band(15, 20)
        except statistics.StatisticsError:
            self.message_log("Set profit Exception, can't calculate BollingerBand, set profit by default",
                             log_level=LogLevel.WARNING)
        else:
            tbb = bb.get('tbb')
            bbb = bb.get('bbb')
            last_price = self.get_buffered_ticker().last_price
        if last_price and tbb and bbb:
            if self.cycle_buy:
                profit = PROFIT_K * 100 * (tbb - last_price) / last_price
            else:
                profit = PROFIT_K * 100 * (last_price - bbb) / last_price
            profit = min(max(profit, PROFIT), PROFIT_MAX)
        else:
            profit = PROFIT
        return Decimal(profit).quantize(Decimal("1.00"), rounding=ROUND_CEILING)

    def calc_profit_order(self, buy_side: bool, by_market: bool = False) -> Dict[str, Decimal]:
        """
        Calculation based on amount value
        :param buy_side: for take profit order, inverse to current cycle
        :param by_market:
        :return:
        """
        self.message_log(f"calc_profit_order: buy_side: {buy_side}, by_market: {by_market}", LogLevel.DEBUG)
        tcm = self.get_trading_capability_manager()
        # Calculate take profit order
        if PROFIT_MAX:
            profit = self.set_profit()
        else:
            profit = PROFIT
        if by_market:
            fee = FEE_TAKER
        else:
            fee = FEE_MAKER
        fee = fee if FEE_IN_PAIR else fee + FEE_MAKER
        if buy_side:
            # Calculate target amount for first
            self.tp_amount = self.sum_amount_first
            target_amount_first = self.sum_amount_first + (fee + profit) * self.sum_amount_first / 100
            target_amount_first = self.round_truncate(target_amount_first, base=True, _rounding=ROUND_CEILING)
            target = target_amount_first
            self.message_log(f"calc_profit_order.target_amount_first: {target_amount_first}",
                             log_level=LogLevel.DEBUG)
            # Calculate depo amount in second
            amount_s = self.round_truncate(self.sum_amount_second, base=False, _rounding=ROUND_FLOOR)
            price = amount_s / target_amount_first
            price = float2decimal(tcm.round_price(float(price), RoundingType.FLOOR))
            amount = amount_s / price
            amount = self.round_truncate(amount, base=True, _rounding=ROUND_FLOOR)
        else:
            # Calculate target amount for second
            self.tp_amount = self.sum_amount_second
            target_amount_second = self.sum_amount_second + (fee + profit) * self.sum_amount_second / 100
            target_amount_second = self.round_truncate(target_amount_second, base=False, _rounding=ROUND_CEILING)
            target = target_amount_second
            self.message_log(f"calc_profit_order.target_amount_second: {target_amount_second}",
                             log_level=LogLevel.DEBUG)
            # Calculate depo amount in second
            amount = self.round_truncate(self.sum_amount_first, base=True, _rounding=ROUND_FLOOR)
            price = target_amount_second / amount
            price = float2decimal(tcm.round_price(float(price), RoundingType.CEIL))
        self.tp_init = (self.sum_amount_first, self.sum_amount_second)
        self.message_log(f"calc_profit_order: Initial depo for TP: {self.tp_amount}", log_level=LogLevel.DEBUG)
        return {'price': price, 'amount': amount, 'profit': profit, 'target': target}

    def calc_over_price(self,
                        buy_side: bool,
                        depo: float,
                        base_price: float,
                        reverse_target_amount: float,
                        exactly: bool = False) -> float:
        self.message_log(f"calc_over_price: buy_side: {buy_side}, depo: {depo}, base_price: {base_price},"
                         f" reverse_target_amount: {reverse_target_amount},"
                         f" exactly: {exactly}", log_level=LogLevel.DEBUG)
        # Calculate over price for depo refund after Reverse cycle
        # Coarse Search y = kx + b and calculate over_price for target return amount
        over_price = 0.0
        b = self.calc_grid_avg(buy_side, depo, base_price, over_price)
        # print('calc_grid_avg(0): {}'.format(b))
        over_price = 50.0
        grid_amount_50 = self.calc_grid_avg(buy_side, depo, base_price, over_price)
        # print('calc_grid_avg(50): {}'.format(grid_amount_50))
        k = (grid_amount_50 - b) / over_price
        over_price = (reverse_target_amount - b) / k
        # print('over_price coarse: {}'.format(over_price))
        # Fine calculate over_price for target return amount
        if exactly and over_price > 0.0:
            i = 0
            while True:
                dy = reverse_target_amount - self.calc_grid_avg(buy_side, depo, base_price, over_price)
                # print('dy: {}'.format(dy))
                if dy <= 0:
                    return over_price
                dx = dy / k
                over_price += dx
                i += 1
        return over_price

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

    def calc_grid_avg(self, buy_side: bool, depo: float, base_price: float, over_price: float) -> float:
        # self.message_log(f"calc_grid_avg: buy_side: {buy_side}, depo: {depo}, base_price: {base_price},"
        #                  f" over_price: {over_price}", log_level=LogLevel.DEBUG)
        # Calculate return average amount in second coin for grid orders with fixed initial parameters
        martin_float = float(self.martin)
        if buy_side:
            depo = depo * base_price
        tcm = self.get_trading_capability_manager()
        delta_price = (over_price * base_price) / (100 * (self.order_q - 1))
        avg_amount = 0.0
        for i in range(self.order_q):
            price_k = 1 - math.log(self.order_q - i, self.order_q)
            if buy_side:
                price = base_price - i * delta_price * price_k
            else:
                price = base_price + i * delta_price * price_k
            price = tcm.round_price(price, RoundingType.ROUND)
            amount = depo * pow(martin_float, i) * (1 - martin_float) / (1 - pow(martin_float, self.order_q))
            amount = tcm.round_amount(amount, RoundingType.FLOOR)
            # print(f"calc_grid_avg.amount: {amount}")
            if buy_side:
                amount /= price
                avg_amount += amount
            else:
                avg_amount += amount * price
        return avg_amount

    def start_process(self):
        # Init analytic
        self.connection_analytic = self.connection_analytic or sqlite3.connect(WORK_PATH + 'funds_rate.db',
                                                                               check_same_thread=False)
        # Create processes for save to .db and send Telegram message
        self.pr_db = Thread(target=save_to_db, args=(self.queue_to_db,))
        self.pr_tlg = Thread(target=telegram, args=(self.queue_to_tlg,))
        if not self.pr_db.is_alive():
            print('Start process for .db save')
            try:
                self.pr_db.start()
            except AssertionError as error:
                self.message_log(str(error), log_level=LogLevel.ERROR, color=Style.B_RED)
        if not self.pr_tlg.is_alive():
            print('Start process for Telegram')
            try:
                self.pr_tlg.start()
            except AssertionError as error:
                self.message_log(str(error), log_level=LogLevel.ERROR, color=Style.B_RED)

    def fee_for_grid(self, amount_first: Decimal, amount_second: Decimal,
                     by_market: bool = False) -> (Decimal, Decimal):
        """
        Calculate trade amount with Fee for grid order for both currency
        """
        if FEE_IN_PAIR:
            if by_market:
                fee = FEE_TAKER
            else:
                fee = FEE_MAKER
            if FEE_BNB_IN_PAIR:
                if self.cycle_buy:
                    amount_first -= self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                        _rounding=ROUND_CEILING)
                    self.message_log(f"For grid order First - fee: {amount_first}", log_level=LogLevel.DEBUG)
                else:
                    amount_first += self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                        _rounding=ROUND_CEILING)
                    self.message_log(f"For grid order First + fee: {amount_first}", log_level=LogLevel.DEBUG)
            else:
                if self.cycle_buy:
                    if FEE_SECOND:
                        amount_second += self.round_truncate(fee * amount_second / 100, base=False, fee=True,
                                                             _rounding=ROUND_CEILING)
                        self.message_log(f"For grid order Second + fee: {amount_second}", log_level=LogLevel.DEBUG)
                    else:
                        amount_first -= self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                            _rounding=ROUND_CEILING)
                        self.message_log(f"For grid order First - fee: {amount_first}", log_level=LogLevel.DEBUG)
                else:
                    amount_second -= self.round_truncate(fee * amount_second / 100, base=False, fee=True,
                                                         _rounding=ROUND_CEILING)
                    self.message_log(f"For grid order Second - fee: {amount_second}", log_level=LogLevel.DEBUG)
        return amount_first, amount_second

    def fee_for_tp(self, amount_first: Decimal, amount_second: Decimal, by_market: bool = False) -> (Decimal, Decimal):
        """
        Calculate trade amount with Fee for take profit order for both currency
        """
        if by_market:
            fee = FEE_TAKER
        else:
            fee = FEE_MAKER
        if FEE_IN_PAIR:
            if FEE_BNB_IN_PAIR:
                if self.cycle_buy:
                    amount_first += self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                        _rounding=ROUND_CEILING)
                    self.message_log(f"Take profit order First + fee: {amount_first}", log_level=LogLevel.DEBUG)
                else:
                    amount_first -= self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                        _rounding=ROUND_CEILING)
                    self.message_log(f"Take profit order First - fee: {amount_first}", log_level=LogLevel.DEBUG)
            else:
                if self.cycle_buy:
                    amount_second -= self.round_truncate(fee * amount_second / 100, base=False, fee=True,
                                                         _rounding=ROUND_CEILING)
                    self.message_log(f"Take profit order Second - fee: {amount_second}", log_level=LogLevel.DEBUG)
                else:
                    if FEE_SECOND:
                        amount_second += self.round_truncate(fee * amount_second / 100, base=False, fee=True,
                                                             _rounding=ROUND_CEILING)
                        self.message_log(f"Take profit order Second + fee: {amount_second}", log_level=LogLevel.DEBUG)
                    else:
                        amount_first -= self.round_truncate(fee * amount_first / 100, base=True, fee=True,
                                                            _rounding=ROUND_CEILING)
                        self.message_log(f"Take profit order First - fee: {amount_first}", log_level=LogLevel.DEBUG)
        elif self.reverse:
            if self.cycle_buy:
                amount_second -= self.round_truncate(2 * fee * amount_second / 100, base=False, fee=True,
                                                     _rounding=ROUND_CEILING)
                self.message_log(f"Take profit order Second - fee: {amount_second}", log_level=LogLevel.DEBUG)
            else:
                amount_first -= self.round_truncate(2 * fee * amount_first / 100, base=True, fee=True,
                                                    _rounding=ROUND_CEILING)
                self.message_log(f"Take profit order First - fee: {amount_first}", log_level=LogLevel.DEBUG)
        return self.round_truncate(amount_first, base=True), self.round_truncate(amount_second, base=False)

    def after_filled_tp(self, one_else_grid: bool = False):
        """
        After filling take profit order calculate profit, deposit and restart or place additional TP
        """
        # noinspection PyTupleAssignmentBalance
        amount_first, amount_second, by_market = self.tp_was_filled  # skipcq: PYL-W0632
        self.message_log(f"after_filled_tp: amount_first: {amount_first}, amount_second: {amount_second},"
                         f" by_market: {by_market}, tp_amount: {self.tp_amount}, tp_target: {self.tp_target}"
                         f" one_else_grid: {one_else_grid}", log_level=LogLevel.DEBUG)
        self.debug_output()
        amount_first_fee, amount_second_fee = self.fee_for_tp(amount_first, amount_second, by_market)
        # Calculate cycle and total profit, refresh depo
        if self.cycle_buy:
            profit_second = self.round_truncate(amount_second_fee - self.tp_amount, base=False)
            profit_reverse = self.round_truncate(PROFIT_REVERSE * profit_second if self.reverse else Decimal('0'),
                                                 base=False)
            profit_second -= profit_reverse
            self.profit_second += profit_second
            self.part_profit_second = Decimal('0')
            self.message_log(f"Cycle profit second {self.profit_second} + {profit_reverse}")
        else:
            profit_first = self.round_truncate(amount_first_fee - self.tp_amount, base=True)
            profit_reverse = self.round_truncate(PROFIT_REVERSE * profit_first if self.reverse else Decimal('0'),
                                                 base=True)
            profit_first -= profit_reverse
            self.profit_first += profit_first
            self.part_profit_first = Decimal('0')
            self.message_log(f"Cycle profit first {self.profit_first} + {profit_reverse}")
        transfer_sum_amount_first = Decimal('0')
        transfer_sum_amount_second = Decimal('0')
        if one_else_grid:
            self.message_log("Some grid orders was execute after TP was filled", tlg=True)
            # Correction sum_amount
            self.message_log(f"Before Correction: Sum_amount_first: {self.sum_amount_first},"
                             f" Sum_amount_second: {self.sum_amount_second}",
                             log_level=LogLevel.DEBUG, color=Style.MAGENTA)
            self.sum_amount_first -= self.tp_init[0]
            self.sum_amount_second -= self.tp_init[1]
            self.message_log(f"Sum_amount_first: {self.sum_amount_first}, Sum_amount_second: {self.sum_amount_second}",
                             log_level=LogLevel.DEBUG, color=Style.MAGENTA)
            self.tp_was_filled = ()
            # Return depo in turnover without loss
            tcm = self.get_trading_capability_manager()
            if self.cycle_buy:
                min_trade_amount = tcm.get_min_buy_amount(float(self.avg_rate))
                amount = self.tp_init[1]
                if self.reverse:
                    reverse_target_amount = (float2decimal(self.reverse_target_amount) *
                                             self.tp_init[0] / self.reverse_init_amount)
                else:
                    reverse_target_amount = self.tp_init[0] + (FEE_MAKER * 2 + PROFIT) * self.tp_init[0] / 100
                first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin ** ORDER_Q)
                first_order_vlm /= self.avg_rate
            else:
                min_trade_amount = tcm.get_min_sell_amount(float(self.avg_rate))
                amount = self.tp_init[0]
                if self.reverse:
                    reverse_target_amount = (float2decimal(self.reverse_target_amount) *
                                             self.tp_init[1] / self.reverse_init_amount)
                else:
                    reverse_target_amount = self.tp_init[1] + (FEE_MAKER * 2 + PROFIT) * self.tp_init[1] / 100
                first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin ** ORDER_Q)
            self.message_log(f"Min trade amount is: {min_trade_amount}")
            self.debug_output()
            self.message_log(f"For additional grid amount: {amount}, reverse_target_amount: {reverse_target_amount}",
                             tlg=True)
            if float(first_order_vlm) > min_trade_amount:
                self.message_log("Place additional grid orders and replace TP", tlg=True)
                self.tp_hold_additional = True
                self.place_grid(self.cycle_buy, amount, float(reverse_target_amount), allow_grid_shift=False)
                return
            if float(amount) > min_trade_amount:  # skipcq: PYL-R1705
                self.message_log("Too small amount for place additional grid, correct grid and replace TP", tlg=True)
                if self.orders_hold:
                    order = self.orders_hold.orders_list.pop()
                    order['amount'] += self.tp_init[1] if self.cycle_buy else self.tp_init[0]
                    self.message_log(f"Corrected amount of last hold grid order: {order['amount']}")
                    self.orders_hold.orders_list.append(order)
                elif self.orders_grid:
                    order = self.orders_grid.orders_list[-1]
                    order['amount'] = self.tp_init[1] if self.cycle_buy else self.tp_init[0]
                    self.message_log(f"Additional grid order for buy: {order['buy']},"
                                     f" {order['amount']} by {order['price']}")
                    waiting_order_id = self.place_limit_order(order['buy'], float(order['amount']),
                                                              float(order['price']))
                    self.orders_init.append(waiting_order_id, order['buy'], order['amount'], order['price'])
                else:
                    self.message_log(f"Additional grid order for buy: {self.cycle_buy},"
                                     f" {amount} by {reverse_target_amount / amount}")
                    waiting_order_id = self.place_limit_order(self.cycle_buy, float(amount),
                                                              float(reverse_target_amount / amount))
                    self.orders_init.append(waiting_order_id, self.cycle_buy, amount, reverse_target_amount / amount)
                self.place_profit_order(by_market=by_market)
                return
            else:
                self.message_log("Too small for trade, transfer filled amount to the next cycle", tlg=True)
                transfer_sum_amount_first = self.sum_amount_first
                transfer_sum_amount_second = self.sum_amount_second
        if self.cycle_buy:
            self.deposit_second += self.profit_second - transfer_sum_amount_second
            if self.reverse:
                self.sum_profit_second += profit_reverse
                self.initial_reverse_first += transfer_sum_amount_first
                self.initial_reverse_second += profit_reverse - transfer_sum_amount_second
            else:
                # Take full profit only for non-reverse cycle
                self.sum_profit_second += self.profit_second
                self.initial_first += transfer_sum_amount_first
                self.initial_second += self.profit_second - transfer_sum_amount_second
            self.message_log(f"after_filled_tp: new initial_funding:"
                             f" {self.initial_reverse_second if self.reverse else self.initial_second}",
                             log_level=LogLevel.DEBUG)
            self.cycle_buy_count += 1
        else:
            self.deposit_first += self.profit_first - transfer_sum_amount_first
            if self.reverse:
                self.sum_profit_first += profit_reverse
                self.initial_reverse_first += profit_reverse - transfer_sum_amount_first
                self.initial_reverse_second += transfer_sum_amount_second
            else:
                # Take full account profit only for non-reverse cycle
                self.sum_profit_first += self.profit_first
                self.initial_first += self.profit_first - transfer_sum_amount_first
                self.initial_second += transfer_sum_amount_second
            self.message_log(f"after_filled_tp: new initial_funding:"
                             f" {self.initial_reverse_first if self.reverse else self.initial_first}",
                             log_level=LogLevel.DEBUG)
            self.cycle_sell_count += 1
        if (not self.cycle_buy and self.profit_first < 0) or (self.cycle_buy and self.profit_second < 0):
            self.message_log("Strategy have a negative cycle result, STOP", log_level=LogLevel.CRITICAL)
            self.command = 'end'
            self.cancel_grid()
        else:
            self.message_log("Restart after filling take profit order", tlg=False)
        self.debug_output()
        self.restart = True
        self.sum_amount_first = transfer_sum_amount_first
        self.sum_amount_second = transfer_sum_amount_second
        self.part_amount_first = Decimal('0')
        self.part_amount_second = Decimal('0')
        self.correction_amount_first = Decimal('0')
        self.correction_amount_second = Decimal('0')
        self.tp_part_amount_first = Decimal('0')
        self.tp_part_amount_second = Decimal('0')
        self.start()

    def reverse_after_grid_ending(self):
        self.message_log("reverse_after_grid_ending:", log_level=LogLevel.DEBUG)
        self.debug_output()
        if self.reverse:
            self.message_log('End reverse cycle', tlg=True)
            self.reverse = False
            self.restart = True
            # Calculate profit and time for Reverse cycle
            self.cycle_time = self.cycle_time_reverse
            if self.cycle_buy:
                self.profit_first += self.round_truncate(self.sum_amount_first - self.reverse_init_amount +
                                                         self.tp_part_amount_first, base=True)
                self.deposit_first += self.round_truncate(self.profit_first - self.tp_part_amount_first, base=True)
                self.initial_first += self.round_truncate(self.profit_first - self.tp_part_amount_first, base=True)
                self.message_log(f"Reverse cycle profit first {self.profit_first}")
                self.sum_profit_first += self.profit_first
                self.cycle_sell_count += 1
            else:
                self.profit_second += self.round_truncate(self.sum_amount_second - self.reverse_init_amount +
                                                          self.tp_part_amount_second, base=False)
                self.deposit_second += self.round_truncate(self.profit_second - self.tp_part_amount_second, base=False)
                self.initial_second += self.round_truncate(self.profit_second - self.tp_part_amount_second, base=False)
                self.message_log(f"Reverse cycle profit second {self.profit_second}")
                self.sum_profit_second += self.profit_second
                self.cycle_buy_count += 1
            self.cycle_time_reverse = None
            self.reverse_target_amount = None
            self.reverse_init_amount = Decimal('0')
            self.initial_reverse_first = Decimal('0')
            self.initial_reverse_second = Decimal('0')
            self.command = 'stop' if REVERSE_STOP and REVERSE else self.command
            if (self.cycle_buy and self.profit_first <= 0) or (not self.cycle_buy and self.profit_second <= 0):
                self.message_log("Strategy have a negative cycle result, STOP", log_level=LogLevel.CRITICAL)
                self.command = 'end'
        else:
            try:
                adx = self.adx(ADX_CANDLE_SIZE_IN_MINUTES, ADX_NUMBER_OF_CANDLES, ADX_PERIOD)
            except ZeroDivisionError:
                trend_up = True
                trend_down = True
            else:
                trend_up = adx.get('adx') > ADX_THRESHOLD and adx.get('+DI') > adx.get('-DI')
                trend_down = adx.get('adx') > ADX_THRESHOLD and adx.get('-DI') > adx.get('+DI')
                # print('adx: {}, +DI: {}, -DI: {}'.format(adx.get('adx'), adx.get('+DI'), adx.get('-DI')))
            self.cycle_time_reverse = self.cycle_time or datetime.utcnow()
            # Calculate target return amount
            tp = self.calc_profit_order(not self.cycle_buy)
            if self.cycle_buy:
                self.deposit_first = self.round_truncate(self.sum_amount_first, base=True) - self.tp_part_amount_first
                self.reverse_target_amount = float(tp.get('amount') * tp.get('price') - self.tp_part_amount_second)
                self.reverse_init_amount = self.sum_amount_second - self.tp_part_amount_second
                self.initial_reverse_first = self.initial_first + self.sum_amount_first
                self.initial_reverse_second = self.initial_second - self.sum_amount_second
                self.message_log(f"Depo for Reverse cycle first: {self.deposit_first}", log_level=LogLevel.DEBUG,
                                 color=Style.B_WHITE)
            else:
                self.deposit_second = (self.round_truncate(self.sum_amount_second, base=False)
                                       - self.tp_part_amount_second)
                self.reverse_target_amount = float(tp.get('amount') - self.tp_part_amount_first)
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
            self.debug_output()
            self.part_amount_first = Decimal('0')
            self.part_amount_second = Decimal('0')
            self.tp_part_amount_first = Decimal('0')
            self.tp_part_amount_second = Decimal('0')
            self.start()

    def place_grid_part(self) -> None:
        self.grid_place_flag = True
        k = 0
        n = len(self.orders_grid) + len(self.orders_init)
        for i in self.orders_hold:
            if k == GRID_MAX_COUNT or k + n >= ORDER_Q:
                if k + n >= ORDER_Q:
                    self.order_q_placed = True
                break
            waiting_order_id = self.place_limit_order(i['buy'], float(i['amount']), float(i['price']))
            self.orders_init.append(waiting_order_id, i['buy'], i['amount'], i['price'])
            k += 1
        del self.orders_hold.orders_list[:k]

    def grid_only_stop(self) -> None:
        tcm = self.get_trading_capability_manager()
        self.avg_rate = self.sum_amount_second / self.sum_amount_first
        self.avg_rate = float2decimal(tcm.round_price(float(self.avg_rate), RoundingType.FLOOR))
        if self.cycle_buy:
            self.message_log('Stop after buy asset\n'
                             'Sell {} {}\n'
                             'Buy {} {}\n'
                             'Average rate is {}'
                             .format(self.sum_amount_second, self.s_currency,
                                     self.sum_amount_first, self.f_currency, self.avg_rate), tlg=True)
        else:
            self.message_log('Stop after sell asset\n'
                             'Buy {} {}\n'
                             'Sell {} {}\n'
                             'Average rate is {}'
                             .format(self.sum_amount_second, self.s_currency,
                                     self.sum_amount_first, self.f_currency, self.avg_rate), tlg=True)
        self.command = 'stop'
        self.restart = True
        self.start()

    def grid_handler(self, _amount_first=None, _amount_second=None, by_market: bool = False,
                     after_full_fill: bool = True) -> None:
        """
        Handler after filling grid order
        """
        if after_full_fill and _amount_first:
            # Calculate trade amount with Fee
            amount_first_fee, amount_second_fee = self.fee_for_grid(_amount_first, _amount_second, by_market)
            # Calculate cycle sum trading for both currency
            self.sum_amount_first += amount_first_fee + self.part_amount_first
            self.sum_amount_second += amount_second_fee + self.part_amount_second
            self.part_amount_first = Decimal('0')
            self.part_amount_second = Decimal('0')
            self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                             f" Sum_amount_second: {self.sum_amount_second}",
                             log_level=LogLevel.DEBUG, color=Style.MAGENTA)
        # State
        no_grid = not self.orders_grid and not self.orders_hold and not self.orders_init
        if no_grid and not self.orders_save:
            if self.tp_order_id:
                self.tp_hold = False
                self.tp_cancel_from_grid_handler = True
                if not self.cancel_order_id:
                    self.cancel_order_id = self.tp_order_id
                    self.cancel_order(self.tp_order_id)
                return
            if self.tp_wait_id:
                # Wait tp order and cancel in on_cancel_order_success and restart
                self.tp_cancel_from_grid_handler = True
                return
            if GRID_ONLY:
                self.grid_only_stop()
            elif (self.tp_part_amount_first or self.tp_part_amount_second
                  or self.correction_amount_first or self.correction_amount_second):
                self.message_log("grid_handler: No grid orders after part filled TP, converse TP to grid", tlg=True)
                # Correction sum_amount
                self.message_log(f"Before Correction: Sum_amount_first: {self.sum_amount_first},"
                                 f" Sum_amount_second: {self.sum_amount_second}",
                                 log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                self.sum_amount_first -= self.tp_part_amount_first
                self.sum_amount_second -= self.tp_part_amount_second
                self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                                 f" Sum_amount_second: {self.sum_amount_second}",
                                 log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                self.tp_part_amount_first += self.correction_amount_first
                self.tp_part_amount_second += self.correction_amount_second
                self.correction_amount_first = Decimal('0')
                self.correction_amount_second = Decimal('0')
                tcm = self.get_trading_capability_manager()
                # Return depo in turnover without loss
                self.message_log(f"Saved TP part amount was: first: {self.tp_part_amount_first},"
                                 f" second: {self.tp_part_amount_second}", log_level=LogLevel.DEBUG)
                _amount_f = self.tp_part_amount_first
                _amount_s = self.tp_part_amount_second
                self.tp_part_amount_first = Decimal('0')
                self.tp_part_amount_second = Decimal('0')
                if self.cycle_buy:
                    min_trade_amount = tcm.get_min_buy_amount(float(self.avg_rate))
                    amount = _amount_s
                    if self.reverse:
                        reverse_target_amount = (float2decimal(self.reverse_target_amount) *
                                                 _amount_f / self.reverse_init_amount)
                    else:
                        reverse_target_amount = _amount_f + (FEE_MAKER * 2 + PROFIT) * _amount_f / 100
                    first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin**ORDER_Q)
                    first_order_vlm /= self.avg_rate
                else:
                    min_trade_amount = tcm.get_min_sell_amount(float(self.avg_rate))
                    amount = _amount_f
                    if self.reverse:
                        reverse_target_amount = (float2decimal(self.reverse_target_amount) *
                                                 _amount_s / self.reverse_init_amount)
                    else:
                        reverse_target_amount = _amount_s + (FEE_MAKER * 2 + PROFIT) * _amount_s / 100
                    first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin**ORDER_Q)
                self.message_log(f"Min trade amount is: {min_trade_amount}")
                self.debug_output()
                self.message_log(f"For additional grid amount: {amount},"
                                 f" reverse_target_amount: {reverse_target_amount}", tlg=True)
                if float(first_order_vlm) > min_trade_amount:
                    self.message_log("Place additional grid orders", tlg=True)
                    self.place_grid(self.cycle_buy, amount, float(reverse_target_amount), allow_grid_shift=False)
                    return
                if float(amount) > min_trade_amount:
                    self.message_log("Too small amount for place additional grid, correct grid", tlg=True)
                    if self.orders_hold:
                        order = self.orders_hold.orders_list.pop()
                        order['amount'] += self.tp_init[1] if self.cycle_buy else self.tp_init[0]
                        self.message_log(f"Corrected amount of last hold grid order: {order['amount']}")
                        self.orders_hold.orders_list.append(order)
                    elif self.orders_grid:
                        order = self.orders_grid.orders_list[-1]
                        order['amount'] = self.tp_init[1] if self.cycle_buy else self.tp_init[0]
                        self.message_log(f"Additional grid order for buy: {order['buy']},"
                                         f" {order['amount']} by {order['price']}")
                        waiting_order_id = self.place_limit_order(order['buy'], float(order['amount']),
                                                                  float(order['price']))
                        self.orders_init.append(waiting_order_id, order['buy'], order['amount'], order['price'])
                    else:
                        self.message_log(f"Additional grid order for buy: {self.cycle_buy},"
                                         f" {amount} by {reverse_target_amount / amount}")
                        waiting_order_id = self.place_limit_order(self.cycle_buy, float(amount),
                                                                  float(reverse_target_amount / amount))
                        self.orders_init.append(waiting_order_id, self.cycle_buy, amount,
                                                reverse_target_amount / amount)
                    return
            elif self.tp_was_filled:
                self.message_log("grid_handler: Was filled TP and all grid orders, converse TP to grid", tlg=True)
                self.after_filled_tp(one_else_grid=True)
            else:
                # Ended grid order, calculate depo and Reverse
                self.reverse_after_grid_ending()
        else:
            if self.orders_save:
                self.grid_remove = False
                self.start_hold = False
                self.message_log("grid_handler: Restore deleted and unplaced grid orders")
                self.orders_hold.orders_list.extend(self.orders_save)
                # Sort restored hold orders
                if self.cycle_buy:
                    self.orders_hold.orders_list.sort(key=lambda x: x['price'], reverse=True)
                else:
                    self.orders_hold.orders_list.sort(key=lambda x: x['price'], reverse=False)
                self.orders_save.orders_list.clear()
                self.order_q_placed = False
            if after_full_fill and self.orders_hold and self.order_q_placed:
                # PLace one hold grid order and remove it from hold list
                _buy, _amount, _price = self.orders_hold.get_first()
                waiting_order_id = self.place_limit_order(_buy, float(_amount), float(_price))
                self.orders_init.append(waiting_order_id, _buy, _amount, _price)
                del self.orders_hold.orders_list[0]
            # Exist filled but non processing TP
            if self.tp_was_filled:
                self.after_filled_tp(one_else_grid=True)
            else:
                self.place_profit_order(by_market)

    def cancel_grid(self):
        """
        Atomic cancel grid orders. Before start() all grid orders must be confirmed canceled
        """
        if self.grid_remove is None:
            self.message_log("cancel_grid: Started", log_level=LogLevel.DEBUG)
            self.grid_remove = True
        if self.grid_remove:
            self.message_log("cancel_grid:", log_level=LogLevel.DEBUG)
            # Temporary save and clear hold orders avoid placing them
            if self.orders_hold:
                self.orders_save.orders_list.extend(self.orders_hold)
                self.orders_hold.orders_list.clear()
            if self.orders_init:
                # Exist not accepted grid order(s), wait msg from exchange
                self.start_hold = True
            elif self.orders_grid:
                # Sequential removal orders from grid and make this 'atomic'
                # - on_cancel_order_success: save canceled order to orders_save
                _id = self.orders_grid.orders_list[0]['id']
                self.message_log(f"cancel_grid order: {_id}", log_level=LogLevel.DEBUG)
                self.grid_order_canceled = _id
                self.cancel_order(_id)
            elif self.grid_remove:
                self.message_log("cancel_grid: Ended", log_level=LogLevel.DEBUG)
                self.grid_remove = None
                self.orders_save.orders_list.clear()
                if self.tp_was_filled:
                    self.after_filled_tp(one_else_grid=False)
                else:
                    self.start()
            else:
                self.grid_remove = None
        else:
            self.grid_remove = None

    def round_truncate(self, _x: Decimal, base: bool, fee: bool = False, _rounding=ROUND_FLOOR) -> Decimal:
        round_pattern = "1.01234567" if fee else self.round_base if base else self.round_quote
        xr = _x.quantize(Decimal(round_pattern), rounding=_rounding)
        return xr

    def debug_output(self):
        self.message_log(f"\n"
                         f"! =======================================\n"
                         f"! debug output:\n"
                         f"! sum_amount_first: {self.sum_amount_first}, sum_amount_second: {self.sum_amount_second}\n"
                         f"! part_amount_first: {self.part_amount_first},"
                         f" part_amount_second: {self.part_amount_second}\n"
                         f"! initial_first: {self.initial_first}, initial_second: {self.initial_second}\n"
                         f"! initial_reverse_first: {self.initial_reverse_first},"
                         f" initial_reverse_second: {self.initial_reverse_second}\n"
                         f"! reverse_init_amount: {self.reverse_init_amount}\n"
                         f"! reverse_target_amount: {self.reverse_target_amount}\n"
                         f"! correction_amount_first: {self.correction_amount_first},"
                         f" correction_amount_second: {self.correction_amount_second}\n"
                         f"! tp_order: {self.tp_order}\n"
                         f"! tp_part_amount_first: {self.tp_part_amount_first},"
                         f" tp_part_amount_second: {self.tp_part_amount_second}\n"
                         f"! profit_first: {self.profit_first}, profit_second: {self.profit_second}\n"
                         f"! part_profit_first: {self.part_profit_first},"
                         f" part_profit_second: {self.part_profit_second}\n"
                         f"! deposit_first: {self.deposit_first}, deposit_second: {self.deposit_second}\n"
                         f"! command: {self.command}\n"
                         f"! reverse: {self.reverse}\n"
                         f"! ======================================")

    def check_order_status(self):
        market_orders = self.get_buffered_open_orders()
        market_orders_id = []
        for order in market_orders:
            market_orders_id.append(order.id)
        strategy_orders_id = self.orders_grid.get_id_list()
        if self.tp_order_id and not self.cancel_order_id:
            strategy_orders_id.append(self.tp_order_id)
        if self.grid_order_canceled:
            try:
                strategy_orders_id.remove(self.grid_order_canceled)
            except ValueError:
                pass
        diff_id = list(set(strategy_orders_id).difference(market_orders_id))
        if diff_id:
            self.message_log(f"Orders not present on exchange: {diff_id}", tlg=True)
            if diff_id.count(self.tp_order_id):
                diff_id.remove(self.tp_order_id)
                amount_first = float2decimal(self.tp_order[1])
                amount_second = float2decimal(self.tp_order[1]) * float2decimal(self.tp_order[2])
                self.tp_was_filled = (amount_first, amount_second, True,)
                self.tp_order_id = None
                self.tp_order = ()
                self.message_log(f"Was filled TP: {self.tp_was_filled}", log_level=LogLevel.DEBUG)
            if diff_id:
                self.shift_grid_threshold = None
                amount_first = Decimal('0')
                amount_second = Decimal('0')
                for _id in diff_id:
                    _buy, _amount, _price = self.orders_grid.get_by_id(_id)
                    self.orders_grid.remove(_id)
                    amount_first += float2decimal(_amount)
                    amount_second += float2decimal(_amount) * float2decimal(_price)
                self.avg_rate = amount_second / amount_first
                self.message_log(f"Grid amount: First: {amount_first}, Second: {amount_second},"
                                 f" price: {self.avg_rate}")
                self.grid_handler(_amount_first=amount_first, _amount_second=amount_second,
                                  after_full_fill=True)
            elif self.tp_was_filled:
                self.cancel_grid()

    def check_min_amount_for_tp(self) -> bool:
        res = False
        if self.avg_rate:
            tcm = self.get_trading_capability_manager()
            if self.cycle_buy:
                min_trade_amount = float2decimal(tcm.get_min_sell_amount(float(self.avg_rate)))
                amount = self.sum_amount_first
                amount = self.round_truncate(amount, base=True)
                if amount:
                    self.message_log(f"Sell amount: {amount}, min sell amount: {min_trade_amount}",
                                     log_level=LogLevel.DEBUG)
            else:
                min_trade_amount = float2decimal(tcm.get_min_buy_amount(float(self.avg_rate)))
                amount = self.sum_amount_second / self.avg_rate
                amount = self.round_truncate(amount, base=True)
                if amount:
                    self.message_log(f"Buy amount: {amount}, min buy amount: {min_trade_amount}",
                                     log_level=LogLevel.DEBUG)
            if amount >= min_trade_amount:
                res = True
        return res

    ##############################################################
    # public data update methods
    ##############################################################
    def on_new_ticker(self, ticker: Ticker) -> None:
        # print(f"on_new_ticker:ticker.last_price: {ticker.last_price}")
        if (self.shift_grid_threshold and self.last_shift_time and time.time() - self.last_shift_time > SHIFT_GRID_DELAY
            and ((self.cycle_buy and ticker.last_price >= self.shift_grid_threshold)
                 or
                 (not self.cycle_buy and ticker.last_price <= self.shift_grid_threshold))):
            if not STANDALONE and EXTRA_CHECK_ORDER_STATE:
                self.check_order_status()
            if self.shift_grid_threshold:
                self.message_log('Shift grid', color=Style.B_WHITE)
                self.shift_grid_threshold = None
                self.start_after_shift = True
                if self.part_amount_first != 0 or self.part_amount_second != 0:
                    self.message_log("Grid order was small partially filled, correct depo")
                    if self.cycle_buy:
                        self.deposit_second += self.round_truncate(self.part_amount_second, base=False)
                        self.message_log(f"New second depo: {self.deposit_second}")
                    else:
                        self.deposit_first += self.round_truncate(self.part_amount_first, base=True)
                        self.message_log(f"New first depo: {self.deposit_first}")
                    self.part_amount_first = Decimal('0')
                    self.part_amount_second = Decimal('0')
                self.grid_remove = None
                self.cancel_grid()

    def on_new_order_book(self, order_book: OrderBook) -> None:
        # print(f"on_new_order_book: max_bids: {order_book.bids[0].price}, min_asks: {order_book.asks[0].price}")
        pass

    def on_new_funds(self, funds: Dict[str, FundsEntry]) -> None:
        # print(f"on_new_funds.funds: {funds}")
        ff = funds.get(self.f_currency, 0)
        fs = funds.get(self.s_currency, 0)
        if self.wait_refunding_for_start:
            ff = float2decimal(ff.total_for_currency) if ff else Decimal('0.0')
            fs = float2decimal(fs.total_for_currency) if fs else Decimal('0.0')
            if self.reverse:
                delta_f = ff - self.initial_reverse_first
                delta_s = fs - self.initial_reverse_second
            else:
                delta_f = ff - self.initial_first
                delta_s = fs - self.initial_second
            delta = delta_f * self.avg_rate + delta_s
            tcm = self.get_trading_capability_manager()
            min_delta = float2decimal(0.1 * tcm.get_min_buy_amount(float(self.avg_rate))) * self.avg_rate
            if delta > 0 or delta.copy_abs() < min_delta:
                self.start()
                return
        if self.tp_order_hold:
            if self.tp_order_hold['buy_side']:
                available_fund = float2decimal(fs.available) if fs else Decimal('0.0')
            else:
                available_fund = float2decimal(ff.available) if ff else Decimal('0.0')
            if available_fund >= self.tp_order_hold['amount']:
                self.place_profit_order()
                return
        if self.grid_hold:
            if self.grid_hold['buy_side']:
                available_fund = float2decimal(fs.available) if fs else Decimal('0.0')
            else:
                available_fund = float2decimal(ff.available) if ff else Decimal('0.0')
            if available_fund >= self.grid_hold['depo']:
                self.place_grid(self.grid_hold['buy_side'],
                                self.grid_hold['depo'], self.reverse_target_amount)

    ##############################################################
    # private update methods
    ##############################################################

    def on_order_update(self, update: OrderUpdate) -> None:
        # self.message_log(f"Order {update.original_order.id}: {update.status}", log_level=LogLevel.DEBUG)
        if update.status in [OrderUpdate.ADAPTED,
                             OrderUpdate.NO_CHANGE,
                             OrderUpdate.REAPPEARED,
                             OrderUpdate.DISAPPEARED,
                             OrderUpdate.CANCELED,
                             OrderUpdate.OTHER_CHANGE]:
            pass
        else:
            self.message_log(f"Order {update.original_order.id}: {update.status}", color=Style.B_WHITE)
            result_trades = update.resulting_trades
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            if update.status == OrderUpdate.PARTIALLY_FILLED:
                # Get last trade row
                if result_trades:
                    i = result_trades[-1]
                    amount_first = float2decimal(i.amount)
                    amount_second = float2decimal(i.amount) * float2decimal(i.price)
                    self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
                else:
                    self.message_log(f"No records for {update.original_order.id}", log_level=LogLevel.WARNING)
            else:
                for i in result_trades:
                    # Calculate sum trade amount for both currency
                    amount_first += float2decimal(i.amount)
                    amount_second += float2decimal(i.amount) * float2decimal(i.price)
                    self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
            # Retreat of courses
            if amount_first == 0:
                self.message_log(f"No amount for {update.original_order.id}", log_level=LogLevel.WARNING)
                return
            self.avg_rate = amount_second / amount_first
            self.message_log(f"Executed amount: First: {amount_first}, Second: {amount_second}, price: {self.avg_rate}")
            if update.status in (OrderUpdate.FILLED, OrderUpdate.ADAPTED_AND_FILLED):
                self.shift_grid_threshold = None
                if self.orders_grid.exist(update.original_order.id):
                    # Remove grid order with =id from order list
                    self.orders_grid.remove(update.original_order.id)
                    self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)
                elif self.tp_order_id == update.original_order.id:
                    # Filled take profit order, restart
                    self.tp_order_id = None
                    self.cancel_order_id = None
                    self.tp_order = ()
                    if self.reverse_hold:
                        self.reverse_hold = False
                        self.cycle_time_reverse = None
                        self.initial_reverse_first = Decimal('0')
                        self.initial_reverse_second = Decimal('0')
                        self.message_log("Cancel hold reverse cycle", color=Style.B_WHITE, tlg=True)
                    self.tp_part_amount_first = Decimal('0')
                    self.tp_part_amount_second = Decimal('0')
                    self.tp_was_filled = (amount_first, amount_second, False,)
                    # print(f"on_order_update.was_filled_tp: {self.tp_was_filled}")
                    if self.tp_hold:
                        # After place but before execute TP was filled some grid
                        self.tp_hold = False
                        self.after_filled_tp(one_else_grid=True)
                    elif self.tp_cancel_from_grid_handler:
                        self.tp_cancel_from_grid_handler = False
                        self.grid_handler()
                    else:
                        self.grid_remove = True
                        self.cancel_grid()
                else:
                    self.message_log('Wild order, do not know it', tlg=True)
            elif update.status == OrderUpdate.PARTIALLY_FILLED:
                order_trade = update.original_order
                if self.tp_order_id == order_trade.id:
                    self.message_log("Take profit partially filled", color=Style.B_WHITE)
                    amount_first_fee, amount_second_fee = self.fee_for_tp(amount_first, amount_second)
                    # Calculate profit for filled part TP
                    _profit_first = Decimal('0')
                    _profit_second = Decimal('0')
                    if self.cycle_buy:
                        _profit_second = self.round_truncate(((self.tp_target - self.tp_amount) * amount_second_fee /
                                                              self.tp_target), base=False)
                        self.part_profit_second += _profit_second
                        self.message_log(f"Part profit second {self.part_profit_second}", log_level=LogLevel.DEBUG)
                    else:
                        _profit_first = self.round_truncate(((self.tp_target - self.tp_amount) * amount_first_fee /
                                                             self.tp_target), base=True)
                        self.part_profit_first += _profit_first
                        self.message_log(f"Part profit first {self.part_profit_first}", log_level=LogLevel.DEBUG)
                    self.tp_part_amount_first += amount_first_fee - _profit_first
                    self.tp_part_amount_second += amount_second_fee - _profit_second
                    if self.reverse_hold:
                        self.message_log("Correct hold reverse cycle", color=Style.B_WHITE, tlg=False)
                        if self.cycle_buy:
                            self.message_log(f"Old: reverse_target_amount: {self.reverse_target_amount},"
                                             f" deposit_first: {self.deposit_first},"
                                             f" reverse_init_amount: {self.reverse_init_amount}",
                                             log_level=LogLevel.DEBUG)
                            self.reverse_target_amount -= float(amount_second_fee)
                            self.deposit_first -= amount_first_fee
                            self.reverse_init_amount -= amount_second_fee
                            self.message_log(f"New: reverse_target_amount: {self.reverse_target_amount},"
                                             f" deposit_first: {self.deposit_first},"
                                             f" reverse_init_amount: {self.reverse_init_amount}",
                                             log_level=LogLevel.DEBUG)
                        else:
                            self.message_log(f"Old: reverse_target_amount: {self.reverse_target_amount},"
                                             f" deposit_second: {self.deposit_second},"
                                             f" reverse_init_amount: {self.reverse_init_amount}",
                                             log_level=LogLevel.DEBUG)
                            self.reverse_target_amount -= float(amount_first_fee)
                            self.deposit_second -= amount_second_fee
                            self.reverse_init_amount -= amount_first_fee
                            self.message_log(f"New: reverse_target_amount: {self.reverse_target_amount},"
                                             f" deposit_second: {self.deposit_second},"
                                             f" reverse_init_amount: {self.reverse_init_amount}",
                                             log_level=LogLevel.DEBUG)
                else:
                    self.message_log("Grid order partially filled", color=Style.B_WHITE)
                    amount_first_fee, amount_second_fee = self.fee_for_grid(amount_first, amount_second)
                    # Increase trade result and if next fill order is grid decrease trade result
                    self.sum_amount_first += amount_first_fee
                    self.sum_amount_second += amount_second_fee
                    self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                                     f" Sum_amount_second: {self.sum_amount_second}",
                                     log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                    self.part_amount_first -= amount_first_fee
                    self.part_amount_second -= amount_second_fee
                    self.message_log(f"Part_amount_first: {self.part_amount_first},"
                                     f" Part_amount_second: {self.part_amount_second}", log_level=LogLevel.DEBUG)
                    # Get min trade amount
                    if self.check_min_amount_for_tp():
                        self.shift_grid_threshold = None
                        self.grid_handler(after_full_fill=False)
                    else:
                        self.message_log("Partially trade too small, ignore", color=Style.B_WHITE)

    def on_place_order_success(self, place_order_id: int, order: Order) -> None:
        # print(f"on_place_order_success.place_order_id: {place_order_id}")
        if order.remaining_amount == 0.0:
            self.shift_grid_threshold = None
            # Get actual parameter of last trade order
            market_order = self.get_buffered_completed_trades()
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            self.message_log(f"Order {place_order_id} executed by market", color=Style.B_WHITE)
            for o in market_order:
                if o.order_id == order.id:
                    amount_first += float2decimal(o.amount)
                    amount_second += float2decimal(o.amount) * float2decimal(o.price)
            if not amount_first:
                amount_first += float2decimal(order.amount)
                amount_second += float2decimal(order.amount) * float2decimal(order.price)
            self.avg_rate = amount_second / amount_first
            self.message_log(f"For {order.id} first: {amount_first}, second: {amount_second}, price: {self.avg_rate}")
            if self.orders_init.exist(place_order_id):
                self.message_log(f"Grid order {order.id} execute by market")
                self.orders_init.remove(place_order_id)
                self.message_log(f"Waiting order count is: {len(self.orders_init)}, hold: {len(self.orders_hold)}")
                # Place take profit order
                self.grid_handler(_amount_first=amount_first, _amount_second=amount_second,
                                  by_market=True, after_full_fill=True)
            elif place_order_id == self.tp_wait_id:
                # Take profit order execute by market, restart
                self.tp_wait_id = None
                if self.reverse_hold:
                    self.reverse_hold = False
                    self.cycle_time_reverse = None
                    self.initial_reverse_first = Decimal('0')
                    self.initial_reverse_second = Decimal('0')
                    self.message_log("Cancel hold reverse cycle", color=Style.B_WHITE, tlg=True)
                self.message_log(f"Take profit order {order.id} execute by market")
                self.tp_was_filled = (amount_first, amount_second, True,)
                if self.tp_hold or self.tp_cancel_from_grid_handler:
                    self.tp_cancel_from_grid_handler = False
                    self.tp_hold = False
                    # After place but before accept TP was filled some grid
                    self.after_filled_tp(one_else_grid=True)
                else:
                    self.grid_remove = True
                    self.cancel_grid()
            else:
                self.message_log('Did not have waiting order id for {}'.format(place_order_id),
                                 LogLevel.ERROR, color=Style.B_RED)
        else:
            if self.orders_init.exist(place_order_id):
                self.orders_grid.append(order.id, order.buy, float2decimal(order.amount), float2decimal(order.price))
                if self.cycle_buy:
                    self.orders_grid.orders_list.sort(key=lambda x: x['price'], reverse=True)
                else:
                    self.orders_grid.orders_list.sort(key=lambda x: x['price'], reverse=False)
                # self.message_log(f"on_place_order_success.orders_grid", log_level=LogLevel.DEBUG)
                # for i in self.orders_grid.orders_list: self.message_log(f"orders_grid: {i}", log_level=LogLevel.DEBUG)
                self.orders_init.remove(place_order_id)
                # self.message_log(f"Waiting order count is: {len(self.orders_init)}, hold: {len(self.orders_hold)}")
                if not self.orders_init:
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
                        else:
                            self.last_shift_time = time.time()
                        if self.start_hold:
                            self.message_log('Release hold Start, continue remove grid orders', color=Style.B_WHITE)
                            self.start_hold = False
                            self.grid_remove = True
                            self.cancel_grid()
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None
                self.tp_order_id = order.id
                if self.tp_hold or self.tp_cancel or self.tp_cancel_from_grid_handler:
                    self.cancel_order_id = self.tp_order_id
                    self.cancel_order(self.tp_order_id)
                else:
                    # Place next part of grid orders
                    if self.orders_hold and not self.order_q_placed and not self.orders_init:
                        self.message_log(f"Place next part of grid orders, hold {len(self.orders_hold)}")
                        self.place_grid_part()
            else:
                self.message_log(F"Did not have waiting order id for {place_order_id}", LogLevel.ERROR)

    def on_place_order_error_string(self, place_order_id: int, error: str) -> None:
        # Check all orders on exchange if exists required
        open_orders = self.get_buffered_open_orders(True)  # lgtm [py/call/wrong-arguments]
        order = None
        if self.orders_init.exist(place_order_id):
            order = self.orders_init.find_order(open_orders, place_order_id)
        elif place_order_id == self.tp_wait_id:
            for k, o in enumerate(open_orders):
                if o.buy == self.tp_order[0] and o.amount == self.tp_order[1] and o.price == self.tp_order[2]:
                    order = open_orders[k]
        if order:
            self.on_place_order_success(place_order_id, order)
        else:
            self.message_log(f"On place order {place_order_id} error: {error}", LogLevel.ERROR, tlg=True)
            if self.orders_init.exist(place_order_id):
                _buy, _amount, _price = self.orders_init.get_by_id(place_order_id)
                self.orders_hold.append(place_order_id, _buy, _amount, _price)
                # Sort restored hold orders
                if self.cycle_buy:
                    self.orders_hold.orders_list.sort(key=lambda x: x['price'], reverse=True)
                else:
                    self.orders_hold.orders_list.sort(key=lambda x: x['price'], reverse=False)
                self.orders_init.remove(place_order_id)
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None
                self.tp_error = True

    def on_cancel_order_success(self, order_id: int, canceled_order: Order) -> None:
        if self.orders_grid.exist(order_id):
            self.grid_order_canceled = None
            self.orders_grid.remove(order_id)
            self.orders_save.append(canceled_order.id, canceled_order.buy, float2decimal(canceled_order.amount),
                                    float2decimal(canceled_order.price))
            # for i in self.orders_save: self.message_log(f"on_cancel_order_success.orders_save (after): {i}")
            self.cancel_grid()
        elif order_id == self.cancel_order_id:
            self.cancel_order_id = None
            self.tp_order_id = None
            self.tp_order = ()
            if self.tp_cancel_from_grid_handler:
                self.tp_cancel_from_grid_handler = False
                self.grid_handler()
                return
            if self.tp_part_amount_first or self.tp_part_amount_second:
                # Correct sum_amount
                self.sum_amount_first -= self.tp_part_amount_first
                self.sum_amount_second -= self.tp_part_amount_second
                self.message_log(f"Canceled TP part amount: first: {self.tp_part_amount_first},"
                                 f" second: {self.tp_part_amount_second}",
                                 log_level=LogLevel.DEBUG)
                self.message_log(f"Corrected Sum_amount_first: {self.sum_amount_first},"
                                 f" Sum_amount_second: {self.sum_amount_second}",
                                 log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                # Save correct amount
                self.correction_amount_first += self.tp_part_amount_first
                self.correction_amount_second += self.tp_part_amount_second
                self.tp_part_amount_first = Decimal('0')
                self.tp_part_amount_second = Decimal('0')
                # Save part profit
                self.profit_first += self.part_profit_first
                self.part_profit_first = Decimal('0')
                self.profit_second += self.part_profit_second
                self.part_profit_second = Decimal('0')
            if self.tp_hold:
                self.tp_hold = False
                self.place_profit_order()
                return
            if self.tp_cancel:
                # Restart
                self.tp_cancel = False
                self.start()

    def on_cancel_order_error_string(self, order_id: int, error: str) -> None:
        # Check all orders on exchange if not exists required
        open_orders = self.get_buffered_open_orders(True)  # lgtm [py/call/wrong-arguments]
        if any(i.id == order_id for i in open_orders):
            self.message_log(f"On cancel order {order_id} {error}, try one else", LogLevel.ERROR)
            self.cancel_order(order_id)
        else:
            self.message_log(f"On cancel order {order_id} {error}", LogLevel.ERROR)
            if self.orders_grid.exist(order_id):
                self.message_log("It's was grid order, probably filled", LogLevel.WARNING)
                self.grid_order_canceled = None
                _buy, _amount, _price = self.orders_grid.get_by_id(order_id)
                amount_first = float2decimal(_amount)
                amount_second = float2decimal(_amount) * float2decimal(_price)
                self.avg_rate = amount_second / amount_first
                self.message_log(f"Executed amount: First: {amount_first}, Second: {amount_second},"
                                 f" price: {self.avg_rate}")
                # Remove grid order with =id from order list
                self.orders_grid.remove(order_id)
                self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)
            elif order_id == self.cancel_order_id:
                self.message_log("It's was take profit", LogLevel.ERROR)
                amount_first = float2decimal(self.tp_order[1])
                amount_second = float2decimal(self.tp_order[1]) * float2decimal(self.tp_order[2])
                self.tp_was_filled = (amount_first, amount_second, True,)
                self.tp_order_id = None
                self.tp_order = ()
                self.message_log(f"Was filled TP: {self.tp_was_filled}", log_level=LogLevel.DEBUG)
                self.cancel_grid()
            else:
                self.message_log("It's unknown", LogLevel.ERROR)
