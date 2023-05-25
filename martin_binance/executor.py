####################################################################
# Cyclic grid strategy based on martingale
##################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.18-8"
__maintainer__ = "Jerry Fedorenko"
__contact__ = 'https://github.com/DogsTailFarmer'
##################################################################
import sys
import gc
import statistics
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from threading import Thread
import queue
import requests
from requests.adapters import HTTPAdapter, Retry
# noinspection PyUnresolvedReferences
import traceback  # lgtm [py/unused-import]

from martin_binance import Path, STANDALONE, DB_FILE
# noinspection PyUnresolvedReferences
from martin_binance import WORK_PATH, CONFIG_FILE, LOG_PATH, LAST_STATE_PATH  # lgtm [py/unused-import]

if STANDALONE:
    from martin_binance.margin_wrapper import *  # lgtm [py/polluting-import]
    from martin_binance.margin_wrapper import __version__ as msb_ver
    import psutil
else:
    from margin_strategy_sdk import *  # lgtm [py/polluting-import] skipcq: PY-W2000
    from typing import Dict, List
    import sqlite3
    import time
    import math
    import simplejson as json
    msb_ver = str()
    psutil = None

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
FEE_FTX = bool()
GRID_MAX_COUNT = int()
EXTRA_CHECK_ORDER_STATE = bool()
# Trade parameter
START_ON_BUY = bool()
AMOUNT_FIRST = Decimal()
USE_ALL_FUND = bool()
AMOUNT_SECOND = Decimal()
PRICE_SHIFT = float()
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
# Other
STATUS_DELAY = int()
GRID_ONLY = bool()
LOG_LEVEL_NO_PRINT = []
HOLD_TP_ORDER_TIMEOUT = 30
COLLECT_ASSETS = bool()
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
# Telegram
TELEGRAM_URL = str()
TOKEN = str()
CHANNEL_ID = str()
STOP_TLG = 'stop_signal_QWE#@!'
INLINE_BOT = True
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


def telegram(queue_to_tlg, _bot_id) -> None:
    url = TELEGRAM_URL
    token = TOKEN
    channel_id = CHANNEL_ID
    url += token
    method = url + '/sendMessage'
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[101, 111, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))

    def get_keyboard_markup():
        return json.dumps({
            "inline_keyboard": [
                [
                    {'text': 'status', 'callback_data': 'status_callback'},
                    {'text': 'stop', 'callback_data': 'stop_callback'},
                    {'text': 'end', 'callback_data': 'end_callback'},
                    {'text': 'restart', 'callback_data': 'restart_callback'},
                ]
            ]})

    def requests_post(_method, _data, session, inline_buttons=False):
        if INLINE_BOT and inline_buttons:
            keyboard = get_keyboard_markup()
            _data['reply_markup'] = keyboard

        _res = None
        try:
            _res = session.post(_method, data=_data)
        except requests.exceptions.RetryError as _exc:
            print(f"Telegram: {_exc}")
        except Exception as _exc:
            print(f"Telegram: {_exc}")
        return _res

    def parse_query(update_inner):
        update_id = update_inner.get('update_id')
        query = update_inner.get('callback_query')
        from_id = query.get('from').get('id')

        if from_id != int(channel_id):
            return None

        message = query.get('message')
        message_id = message.get('message_id')
        query_data = query.get('data')
        reply_to_message = message.get('text')

        command = None
        if query_data == 'status_callback':
            command = 'status'
        elif query_data == 'stop_callback':
            command = 'stop'
        elif query_data == 'end_callback':
            command = 'end'
        elif query_data == 'restart_callback':
            command = 'restart'

        requests_post(url + '/answerCallbackQuery', {'callback_query_id': query.get('id')}, s)

        return {
            'update_id': update_id,
            'message_id': message_id,
            'text_in': command,
            'reply_to_message': reply_to_message
        }

    def parse_command(update_inner):
        update_id = update_inner.get('update_id')
        message = update_inner.get('message')
        from_id = message.get('from').get('id')
        if from_id != int(channel_id):
            return None

        message_id = message.get('message_id')
        text_in = update_inner.get('message').get('text')

        try:
            reply_to_message = message.get('reply_to_message').get('text')
        except AttributeError:
            reply_to_message = None
            _text = "The command must be a response to any message from a specific strategy," \
                    " use Reply + Menu combination"
            requests_post(method, _data={'chat_id': channel_id, 'text': _text}, session=s)

        return {
            'update_id': update_id,
            'message_id': message_id,
            'text_in': text_in,
            'reply_to_message': reply_to_message
        }

    def telegram_get(offset=None) -> []:
        command_list = []
        _method = url + '/getUpdates'
        _res = requests_post(_method, _data={'chat_id': channel_id, 'offset': offset}, session=s)
        if not _res or _res.status_code != 200:
            return command_list
        __result = _res.json().get('result')

        for result_in in __result:
            parsed = None
            if result_in.get('message') is not None:
                parsed = parse_command(result_in)
            if result_in.get('callback_query') is not None:
                parsed = parse_query(result_in)
            if parsed:
                command_list.append(parsed)

        return command_list

    def process_update(update_inner, offset=None):
        reply = update_inner.get('reply_to_message')

        if not reply:
            return

        in_bot_id = reply.split('.')[0]
        if in_bot_id != _bot_id:
            return

        try:
            msg_in = str(update_inner['text_in']).lower().strip().replace('/', '')
            if offset and msg_in == 'restart':
                telegram_get(offset_id)
            connection_control.execute('insert into t_control values(?,?,?,?)',
                                       (update_inner['message_id'], msg_in, in_bot_id, None))
            connection_control.commit()
        except sqlite3.Error as ex:
            print(f"telegram: insert into t_control: {ex}")
        else:
            # Send receipt
            post_text = f"Received '{msg_in}' command, OK"
            requests_post(method, _data={'chat_id': channel_id, 'text': post_text}, session=s)

    # Set command for Telegram bot
    _command = requests_post(url + '/getMyCommands', _data=None, session=s)
    if _command and _command.status_code == 200 and (not _command.json().get('result') or
                                                     len(_command.json().get('result')) < 4):
        _commands = {
            "commands": json.dumps([
                {"command": "status",
                 "description": "Get strategy status"},
                {"command": "stop",
                 "description": "Stop strategy after end of cycle, not for Reverse"},
                {"command": "end",
                 "description": "Stop strategy after executed TP order, in Direct and Reverse, all the same"},
                {"command": "restart",
                 "description": "Restart current pair with recovery"}
            ])
        }
        res = requests_post(url + '/setMyCommands', _data=_commands, session=s)
        print(f"Set or update command menu for Telegram bot: code: {res.status_code}, result: {res.json()}, "
              f"restart Telegram bot by /start command for update it")
    #
    connection_control = sqlite3.connect(DB_FILE)
    offset_id = None
    while True:
        try:
            text = queue_to_tlg.get(block=True, timeout=10)
        except KeyboardInterrupt:
            break
        except queue.Empty:
            # Get external command from Telegram bot
            updates = telegram_get(offset_id)
            if not updates:
                continue
            offset_id = updates[-1].get('update_id') + 1
            for update in updates:
                process_update(update, offset_id)
        else:
            if text and STOP_TLG in text:
                connection_control.close()
                break
            requests_post(method, _data={'chat_id': channel_id, 'text': text}, session=s, inline_buttons=True)


def db_management() -> None:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS t_orders (\
                  id_exchange   INTEGER REFERENCES t_exchange (id_exchange)\
                                    ON DELETE RESTRICT ON UPDATE CASCADE NOT NULL,\
                  f_currency    TEXT                NOT NULL,\
                  s_currency    TEXT                NOT NULL,\
                  cycle_buy     BOOLEAN             NOT NULL,\
                  order_buy     INTEGER             NOT NULL,\
                  order_sell    INTEGER             NOT NULL,\
                  order_hold    INTEGER             NOT NULL,\
                  PRIMARY KEY(id_exchange, f_currency, s_currency))")
    conn.commit()
    #
    try:
        conn.execute('SELECT active FROM t_funds LIMIT 1')
    except sqlite3.Error:
        try:
            conn.execute('ALTER TABLE t_funds ADD COLUMN active BOOLEAN DEFAULT 0')
            conn.commit()
        except sqlite3.Error as ex:
            print(f"ALTER table t_funds failed: {ex}")
    #
    cursor = conn.cursor()
    # Compliance check t_exchange and EXCHANGE() = exchange() from ms_cfg.toml
    cursor.execute("SELECT id_exchange, name FROM t_exchange")
    row = cursor.fetchall()
    cursor.close()
    row_n = len(row)
    for i, exch in enumerate(EXCHANGE):
        if i >= row_n:
            print(f"save_to_db: Add exchange {i}, {exch}")
            try:
                conn.execute("INSERT into t_exchange values(?,?)", (i, exch))
                conn.commit()
            except sqlite3.Error as err:
                print(f"INSERT into t_exchange: {err}")
    #
    try:
        conn.execute('UPDATE t_funds SET active = 0 WHERE active = 1')
        conn.commit()
    except sqlite3.Error as ex:
        print(f"Initialise t_funds failed: {ex}")
    conn.close()


def save_to_db(queue_to_db) -> None:
    connection_analytic = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    # Save data to .db
    data = None
    result = True
    while True:
        try:
            if result:
                data = queue_to_db.get()
        except KeyboardInterrupt:
            pass
        if data is None or data.get('stop_signal'):
            break
        if data.get('destination') == 't_funds':
            # print("save_to_db: Record row into t_funds")
            try:
                connection_analytic.execute("INSERT INTO t_funds values(\
                                             ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                                             1,
                                             data.get('cycle_time'),
                                             1))
                connection_analytic.commit()
            except sqlite3.Error as err:
                result = False
                print(f"For save data into t_funds: {err}, retry")
            else:
                result = True
        elif data.get('destination') == 't_orders':
            # print("save_to_db: Record row into t_orders")
            try:
                connection_analytic.execute("INSERT INTO t_orders VALUES(:id_exchange,\
                                                                         :f_currency,\
                                                                         :s_currency,\
                                                                         :cycle_buy,\
                                                                         :order_buy,\
                                                                         :order_sell,\
                                                                         :order_hold)\
                                                ON CONFLICT(id_exchange, f_currency, s_currency)\
                                             DO UPDATE SET cycle_buy=:cycle_buy,\
                                                           order_buy=:order_buy,\
                                                           order_sell=:order_sell,\
                                                           order_hold=:order_hold",
                                            {'id_exchange': ID_EXCHANGE,
                                             'f_currency': data.get('f_currency'),
                                             's_currency': data.get('s_currency'),
                                             'cycle_buy': data.get('cycle_buy'),
                                             'order_buy': data.get('order_buy'),
                                             'order_sell': data.get('order_sell'),
                                             'order_hold': data.get('order_hold')})
                connection_analytic.commit()
            except sqlite3.Error as err:
                print(f"INSERT into t_orders: {err}")
        elif data.get('destination') == 't_funds.active update':
            cursor_analytic = connection_analytic.cursor()
            try:
                cursor_analytic.execute('SELECT 1 FROM t_funds\
                                         WHERE id_exchange =:id_exchange\
                                         AND f_currency =:f_currency\
                                         AND s_currency =:s_currency\
                                         AND active = 1',
                                        {'id_exchange': ID_EXCHANGE,
                                         'f_currency': data.get('f_currency'),
                                         's_currency': data.get('s_currency'),
                                         }
                                        )
                row_active = cursor_analytic.fetchone()
                cursor_analytic.close()
            except sqlite3.Error as err:
                cursor_analytic.close()
                row_active = (2,)
                print(f"SELECT from t_funds: {err}")
            if row_active is None:
                # print("save_to_db: UPDATE t_funds set active=1")
                try:
                    connection_analytic.execute('UPDATE t_funds SET active = 1\
                                                 WHERE id=(SELECT max(id) FROM t_funds\
                                                 WHERE id_exchange=:id_exchange\
                                                 AND f_currency=:f_currency\
                                                 AND s_currency=:s_currency)',
                                                {'id_exchange': ID_EXCHANGE,
                                                 'f_currency': data.get('f_currency'),
                                                 's_currency': data.get('s_currency'),
                                                 }
                                                )
                    connection_analytic.commit()
                except sqlite3.Error as err:
                    print(f"save_to_db: UPDATE t_funds: {err}")
    connection_analytic.commit()


def f2d(_f: float) -> Decimal:
    return Decimal(str(_f))


def solve(fn, value: Decimal, x: Decimal, max_err: Decimal, max_tries=50, **kwargs) -> Decimal:
    """
    Numerical solution of the equation, value = fn(x)
    :param fn: Function
    :param value: Specified value
    :param x: Predict of the search value
    :param max_err:
    :param max_tries:
    :param kwargs: Function parameters as {}
    :return: fine x
    """
    delta = f2d(0.000001)
    solves = []
    tries = 0
    _x = x
    _err = []

    def dx(_fn, _x, _delta, **_kwargs):
        return (_fn(_x + _delta, **_kwargs) - _fn(_x, **_kwargs)) / _delta

    while 1:
        tries += 1
        err = fn(x, **kwargs) - value
        # print(f"tries: {tries}, x: {x}, fn: {fn(x, **kwargs)}, err: {err}")
        if err >= 0 and abs(err) <= max_err:
            print(f"In {tries} attempts the best solution was found!", )
            return x
        correction = (delta * tries) if err < 0 and _err.count(err) else 0
        if err >= 0:
            solves.append((err, x))
        slope = dx(fn, x, delta, **kwargs)
        if slope != 0.0:
            x -= err/slope
            x = max(_x + delta * tries, x + correction)
        else:
            delta *= 10
            if delta > 1:
                break
        # print(f"tries: {tries}, delta: {delta}, correction: {correction}, slope: {slope}")
        if (_err.count(err) or tries > max_tries) and len(solves) > 5:
            solves.sort(key=lambda a: (a[0], a[1]), reverse=False)
            print('Solve return the best of the right value ;-)')
            # print("\n".join(f"delta: {k}\t result: {v}" for k, v in solves))
            return solves[0][1]
        if tries > max_tries * 2:
            break
        _err.append(err)
    print('Oops. No solution found')
    print("\n".join(f"delta: {k}\tresult: {v}" for k, v in solves))
    return f2d(0)


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
        return True, f2d(0), f2d(0)

    def exist(self, _id: int) -> bool:
        return any(i['id'] == _id for i in self.orders_list)

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
        Get Dict[0]  for order
        :return: (buy, amount, price)
        """
        return self.orders_list[0]['buy'], self.orders_list[0]['amount'], self.orders_list[0]['price']

    def get_last(self) -> ():
        """
        Get Dict[-1]  for order
        :return: (buy, amount, price)
        """
        return self.orders_list[-1]['buy'], self.orders_list[-1]['amount'], self.orders_list[-1]['price']

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
        _sum = Decimal('0')
        for i in self.orders_list:
            _sum += i['amount'] * (i['price'] if cycle_buy else 1)
        return _sum


class Strategy(StrategyBase):
    ##############################################################
    # strategy control methods
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
        self.part_amount = {}  # + {order_id: (Decimal(str(amount_f)), Decimal(str(amount_s)))} of partially filled
        self.command = None  # + External input command from Telegram
        self.start_after_shift = False  # - Flag set before shift, clear after place grid
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
        self.reverse_target_amount = REVERSE_TARGET_AMOUNT if REVERSE else Decimal('0')  # + Amount for reverse cycle
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
        self.cycle_status = ()  # - Operational status for current cycle, orders count
        self.grid_update_started = None  # - Flag when grid update process started
        self.start_reverse_time = None  # -
        self.last_ticker_update = 0  # -
        self.grid_only_restart = None  # -

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
            if STANDALONE:
                raise SystemExit(1)
        db_management()
        tcm = self.get_trading_capability_manager()
        self.f_currency = self.get_first_currency()
        self.s_currency = self.get_second_currency()
        self.tlg_header = f"{EXCHANGE[ID_EXCHANGE]}, {self.f_currency}/{self.s_currency}. "
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
            self.message_log(f"Mode for {'buy' if self.cycle_buy else 'sell'} {self.f_currency} by grid orders"
                             f" placement ON",
                             color=Style.B_WHITE)
        # Calculate round float multiplier
        self.round_base = ROUND_BASE or str(tcm.round_amount(1.123456789, RoundingType.FLOOR))
        self.round_quote = ROUND_QUOTE or str(Decimal(self.round_base) *
                                              Decimal(str(tcm.round_price(1.123456789, RoundingType.FLOOR))))
        self.message_log(f"Round pattern, for base: {self.round_base}, quote: {self.round_quote}")
        last_price = self.get_buffered_ticker().last_price
        if last_price:
            self.message_log(f"Last ticker price: {last_price}")
            self.avg_rate = f2d(last_price)
            if self.first_run and check_funds:
                if self.cycle_buy:
                    ds = self.get_buffered_funds().get(self.s_currency, 0)
                    ds = ds.available if ds else 0
                    if USE_ALL_FUND:
                        self.deposit_second = self.round_truncate(f2d(ds), base=False)
                    elif self.deposit_second > f2d(ds):
                        self.message_log('Not enough second coin for Buy cycle!', color=Style.B_RED)
                        if STANDALONE:
                            raise SystemExit(1)
                    depo = self.deposit_second
                else:
                    df = self.get_buffered_funds().get(self.f_currency, 0)
                    df = df.available if df else 0
                    if USE_ALL_FUND:
                        self.deposit_first = self.round_truncate(f2d(df), base=True)
                    elif self.deposit_first > f2d(df):
                        self.message_log('Not enough first coin for Sell cycle!', color=Style.B_RED)
                        if STANDALONE:
                            raise SystemExit(1)
                    depo = self.deposit_first
                if not GRID_ONLY:
                    self.place_grid(self.cycle_buy, depo, self.reverse_target_amount, init_calc_only=True)
        else:
            self.message_log("Can't get actual price, initialization checks stopped", log_level=LogLevel.CRITICAL)
            if STANDALONE:
                raise SystemExit(1)
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
        if stable_state:
            orders = self.get_buffered_open_orders()
            order_buy = len([i for i in orders if i.buy is True])
            order_sell = len([i for i in orders if i.buy is False])
            order_hold = len(self.orders_hold)
            cycle_status = (self.cycle_buy, order_buy, order_sell, order_hold)
            if self.cycle_status != cycle_status:
                self.cycle_status = cycle_status
                data_to_db = {'f_currency': self.f_currency,
                              's_currency': self.s_currency,
                              'cycle_buy': self.cycle_buy,
                              'order_buy': order_buy,
                              'order_sell': order_sell,
                              'order_hold': order_hold,
                              'destination': 't_orders'}
                if self.queue_to_db:
                    # print('Send data to t_orders')
                    self.queue_to_db.put(data_to_db)
        else:
            self.cycle_status = ()
        # endregion
        # region ReportStatus
        # Get command from Telegram
        command = None
        if self.connection_analytic and self.heartbeat_counter % 5 == 0:
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
        if self.command == 'restart':
            self.stop()
            os.execv(sys.executable, [sys.executable] + [sys.argv[0]] + ['1'])
        if command or (STATUS_DELAY and (time.time() - self.status_time) / 60 > STATUS_DELAY):
            # Report current status
            last_price = self.get_buffered_ticker().last_price
            ticker_update = int(time.time()) - self.last_ticker_update
            if self.cycle_time:
                ct = str(datetime.utcnow() - self.cycle_time).rsplit('.')[0]
            else:
                self.message_log("save_strategy_state: cycle_time is None!", log_level=LogLevel.DEBUG)
                ct = str(datetime.utcnow()).rsplit('.')[0]
            if self.command == 'stopped':
                self.message_log("Strategy stopped. Need manual action", tlg=True)
            elif self.grid_hold or self.tp_order_hold:
                funds = self.get_buffered_funds()
                fund_f = funds.get(self.f_currency, 0)
                fund_f = fund_f.available if fund_f else 0
                fund_s = funds.get(self.s_currency, 0)
                fund_s = fund_s.available if fund_s else 0
                if self.grid_hold.get('timestamp'):
                    time_diff = int(time.time() - self.grid_hold['timestamp'])
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
                elif self.tp_order_hold['timestamp']:
                    time_diff = int(time.time() - self.tp_order_hold['timestamp'])
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
                              f"{self.get_free_assets()[2]}"
                              )
                else:
                    header = (f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                              f"For all cycles profit:\n"
                              f"First: {self.sum_profit_first}\n"
                              f"Second: {self.sum_profit_second}\n"
                              f"Summary: {sum_profit}\n"
                              f"{self.get_free_assets(mode='free')[2]}"
                              )
                self.message_log(f"{header}\n"
                                 f"{'*** Shift grid mode ***' if self.shift_grid_threshold else '* ***  ***  *** *'}\n"
                                 f"{'Buy' if self.cycle_buy else 'Sell'}{' Reverse' if self.reverse else ''}"
                                 f"{' Hold reverse' if self.reverse_hold else ''} cycle with"
                                 f" {order_buy} buy and {order_sell} sell active orders.\n"
                                 f"{order_hold if order_hold else 'No'} hold grid orders\n"
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
        self.heartbeat_counter += 1
        if self.heartbeat_counter % 5 == 0 and not STANDALONE and EXTRA_CHECK_ORDER_STATE:
            self.check_order_status()
        if (stable_state
                and ADAPTIVE_TRADE_CONDITION
                and not self.reverse
                and not self.part_amount
                and self.command not in ('stopped', 'stop', 'end')
                and (self.orders_grid or self.orders_hold)):
            if self.heartbeat_counter % 150 == 0:
                self.grid_update(frequency='low')
            elif self.heartbeat_counter % 30 == 0:
                self.grid_update(frequency='mid')
            else:
                self.grid_update(frequency='hi')
        if self.heartbeat_counter > 150:
            self.heartbeat_counter = 0
            # Update t_funds.active set True
            data_to_db = {'f_currency': self.f_currency,
                          's_currency': self.s_currency,
                          'destination': 't_funds.active update'}
            if self.queue_to_db:
                self.queue_to_db.put(data_to_db)
        if self.wait_refunding_for_start or self.tp_order_hold or self.grid_hold:
            self.get_buffered_funds()
        if self.tp_error:
            self.tp_error = False
            self.place_profit_order()
        if self.reverse_hold:
            if self.start_reverse_time:
                if time.time() - self.start_reverse_time > 2 * SHIFT_GRID_DELAY:
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
                        self.tp_part_amount_first = Decimal('0')
                        self.tp_part_amount_second = Decimal('0')
                        self.message_log('Release Hold reverse cycle', color=Style.B_WHITE)
                        self.start()
            else:
                self.start_reverse_time = time.time()
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
            self.deposit_first = f2d(json.loads(strategy_state.get('deposit_first')))
            self.deposit_second = f2d(json.loads(strategy_state.get('deposit_second')))
            self.last_shift_time = json.loads(strategy_state.get('last_shift_time')) or time.time()
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
            self.reverse_target_amount = f2d(json.loads(strategy_state.get('reverse_target_amount')))
            self.shift_grid_threshold = json.loads(strategy_state.get('shift_grid_threshold'))
            self.status_time = json.loads(strategy_state.get('status_time'))
            self.sum_amount_first = f2d(json.loads(strategy_state.get('sum_amount_first')))
            self.sum_amount_second = f2d(json.loads(strategy_state.get('sum_amount_second')))
            self.sum_profit_first = f2d(json.loads(strategy_state.get('sum_profit_first')))
            self.sum_profit_second = f2d(json.loads(strategy_state.get('sum_profit_second')))
            self.tp_amount = f2d(json.loads(strategy_state.get('tp_amount')))
            self.tp_init = eval(json.loads(strategy_state.get('tp_init')))
            self.tp_order_id = json.loads(strategy_state.get('tp_order_id'))
            self.tp_part_amount_first = f2d(json.loads(strategy_state.get('tp_part_amount_first')))
            self.tp_part_amount_second = f2d(json.loads(strategy_state.get('tp_part_amount_second')))
            self.tp_target = f2d(json.loads(strategy_state.get('tp_target')))
            self.tp_order = eval(json.loads(strategy_state.get('tp_order')))
            self.tp_wait_id = json.loads(strategy_state.get('tp_wait_id'))
            self.first_run = False
            self.start_after_shift = False if GRID_ONLY and USE_ALL_FUND else self.start_after_shift
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
        grid_filled = grid_orders_len > 0 and open_orders_len == 0 and not self.orders_hold and not self.orders_save
        tp_no_change = (tp_order and self.tp_order_id) or (not tp_order and not self.tp_order_id)
        tp_placed = tp_order and not self.tp_order_id
        tp_filled = not tp_order and self.tp_order_id
        no_orders = grid_orders_len == 0 and not self.tp_order_id
        #
        part_amount_first = Decimal('0')
        part_amount_second = Decimal('0')
        if grid_filled:
            for v in self.part_amount.values():
                part_amount_first += v[0]
                part_amount_second += v[1]
        #
        self.avg_rate = f2d(self.get_buffered_ticker().last_price)
        #
        if self.command == 'stopped':
            self.message_log("Restore, strategy stopped. Need manual action", tlg=True)
        elif grid_no_change and tp_no_change:
            if grid_hold:
                self.message_log("Restore, no grid orders, place from hold now", tlg=True)
                self.place_grid_part()
            elif no_orders:
                self.restart = True
                self.message_log("Restore, no orders, restart", tlg=True)
                self.start()
            elif not GRID_ONLY and not self.tp_order_id and self.check_min_amount():
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
                    amount_first += f2d(o.amount)
                    amount_second += f2d(o.amount) * f2d(o.price)
            if amount_first == 0:
                # If execution event was missed
                _buy, _amount, _price = self.tp_order
                amount_first = self.round_truncate(_amount, base=True)
                amount_second = self.round_truncate(_amount * _price, base=False)
            self.tp_was_filled = (amount_first, amount_second, True)
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
            amount_first += part_amount_first
            amount_second += part_amount_second
            self.part_amount.clear()
            print(f"Total grid amount first: {amount_first}, second: {amount_second}")
            # Clear list of grid order
            self.orders_grid.orders_list.clear()
            self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)

        elif grid_filled and tp_no_change:
            self.message_log('Restore, No grid orders -> Reverse', tlg=True)
            self.shift_grid_threshold = None
            # Admit that missing orders were executed on conditions no worse than those saved
            # Calculate sum trade amount for both currency
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            for i in self.orders_grid:
                amount_first += i['amount']
                amount_second += i['amount'] * i['price']
                print(f"id={i['id']}, first: {i['amount']}, price: {i['price']}")
            amount_first += part_amount_first
            amount_second += part_amount_second
            self.part_amount.clear()
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
                    amount_first += f2d(o.amount)
                    amount_second += f2d(o.amount) * f2d(o.price)
                    print(f"order_id={o.order_id}, first: {o.amount}, price: {o.price}")
            if amount_first == 0:
                # If execution event was missed
                _buy, _amount, _price = self.tp_order
                amount_first = self.round_truncate(f2d(_amount), base=True)
                amount_second = self.round_truncate(f2d(_amount * _price), base=False)
            self.tp_was_filled = (amount_first, amount_second, True)
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
                    part_amount_first, part_amount_second = self.part_amount.pop(i['id'], (Decimal('0'), Decimal('0')))
            amount_first += part_amount_first
            amount_second += part_amount_second
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
            self.shift_grid_threshold = None
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
                    part_amount_first, part_amount_second = self.part_amount.pop(i['id'], (Decimal('0'), Decimal('0')))
            amount_first += part_amount_first
            amount_second += part_amount_second
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
                    amount_first += f2d(o.amount)
                    amount_second += f2d(o.amount) * f2d(o.price)
                    print(f"order_id={o.order_id}, first: {o.amount}, price: {o.price}")
            if amount_first == 0:
                # If execution event was missed
                _buy, _amount, _price = self.tp_order
                amount_first = self.round_truncate(f2d(_amount), base=True)
                amount_second = self.round_truncate(f2d(_amount * _price), base=False)
            self.tp_was_filled = (amount_first, amount_second, True)
            self.tp_order_id = None
            self.tp_order = ()
            self.grid_remove = True
            self.cancel_grid()

        elif grid_more and self.orders_init:
            self.message_log('Restored, some grid order(s) was placed', tlg=True)

        elif tp_placed:
            self.message_log('Restored, take profit order(s) was placed', tlg=True)

        else:
            self.message_log('Restored, unknown state. Investigation needed', tlg=True)
        # self.unsuspend()

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
                self.cancel_order(self.tp_order_id)
            return
        if self.tp_wait_id:
            # Wait tp order and cancel in on_cancel_order_success and restart
            self.tp_cancel = True
            return
        ff, fs, _x = self.get_free_assets()
        # Save initial funds and cycle statistics to .db for external analytics
        if self.first_run:
            self.start_process()
            self.save_init_assets(ff, fs)
        if self.restart:
            # Check refunding before restart
            if self.cycle_buy:
                go_trade = fs >= self.initial_reverse_second if self.reverse else self.initial_second
                if go_trade:
                    if FEE_IN_PAIR and FEE_MAKER:
                        fs = self.initial_reverse_second if self.reverse else self.initial_second
                    _ff = ff
                    _fs = fs - profit_s
            else:
                go_trade = ff >= self.initial_reverse_first if self.reverse else self.initial_first
                if go_trade:
                    if FEE_IN_PAIR and FEE_MAKER:
                        ff = self.initial_reverse_first if self.reverse else self.initial_first
                    _ff = ff - profit_f
                    _fs = fs
            if go_trade:
                self.wait_refunding_for_start = False
                if not GRID_ONLY:
                    if self.cycle_buy:
                        df = Decimal('0')
                        ds = self.deposit_second - self.profit_second
                    else:
                        df = self.deposit_first - self.profit_first
                        ds = Decimal('0')
                    ct = datetime.utcnow() - self.cycle_time
                    ct = ct.total_seconds()
                    # noinspection PyUnboundLocalVariable
                    data_to_db = {'f_currency': self.f_currency,
                                  's_currency': self.s_currency,
                                  'f_funds': _ff,
                                  's_funds': _fs,
                                  'avg_rate': self.avg_rate,
                                  'cycle_buy': self.cycle_buy,
                                  'f_depo': df,
                                  's_depo': ds,
                                  'f_profit': self.profit_first,
                                  's_profit': self.profit_second,
                                  'order_q': self.order_q,
                                  'over_price': self.over_price,
                                  'cycle_time': ct,
                                  'destination': 't_funds'}
                    if self.queue_to_db:
                        print('Send data to .db t_funds')
                        self.queue_to_db.put(data_to_db)
                self.save_init_assets(ff, fs)
                if STANDALONE and COLLECT_ASSETS:
                    _ff, _fs = self.collect_assets()
                    ff -= _ff
                    fs -= _fs
            else:
                self.wait_refunding_for_start = True
                self.message_log(f"Wait refunding for start, having now: first: {ff}, second: {fs}")
                return
        self.avg_rate = f2d(self.get_buffered_ticker().last_price)
        if GRID_ONLY:
            if USE_ALL_FUND and not self.start_after_shift:
                if self.cycle_buy:
                    self.deposit_second = fs
                    self.message_log(f'Use all available funds: {self.deposit_second} {self.s_currency}')
                else:
                    self.deposit_first = ff
                    self.message_log(f'Use all available funds: {self.deposit_first} {self.f_currency}')
            if not self.check_min_amount(for_tp=False) and self.command is None:
                self.grid_only_restart = True
                self.message_log("Waiting funding for convert", color=Style.B_WHITE)
                return
        if not self.first_run and not self.start_after_shift and not self.reverse and not GRID_ONLY:
            self.message_log(f"Complete {self.cycle_buy_count} buy cycle and {self.cycle_sell_count} sell cycle\n"
                             f"For all cycles profit:\n"
                             f"First: {self.sum_profit_first}\n"
                             f"Second: {self.sum_profit_second}\n"
                             f"Summary: {self.sum_profit_first * self.avg_rate + self.sum_profit_second:f}\n")
        mem = psutil.virtual_memory().percent if psutil else 0
        if mem > 80:
            self.message_log(f"For {VPS_NAME} critical memory availability, end", tlg=True)
            self.command = 'end'
        elif mem > 70:
            self.message_log(f"For {VPS_NAME} low memory availability, stop after end of cycle", tlg=True)
            self.command = 'stop'
        if self.command == 'end' or (self.command == 'stop' and
                                     (not self.reverse or (self.reverse and REVERSE_STOP))):
            self.command = 'stopped'
            self.message_log('Stop, waiting manual action', tlg=True)
        else:
            n = gc.collect(generation=2)
            print('Number of unreachable objects collected by GC:', n)
            self.message_log(f"Initial first: {ff}, second: {fs}", color=Style.B_WHITE)
            self.restart = None
            # Init variable
            self.profit_first = Decimal('0')
            self.profit_second = Decimal('0')
            self.cycle_time = datetime.utcnow()
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
                                     f"{'' if GRID_ONLY else self.get_free_assets(ff, fs, mode='free')[2]}", tlg=True)
            else:
                amount = self.deposit_first
                if start_cycle_output:
                    self.message_log(f"Start Sell{' Reverse' if self.reverse else ''}"
                                     f" {'asset' if GRID_ONLY else 'cycle'} with {amount} {self.f_currency} depo\n"
                                     f"{'' if GRID_ONLY else self.get_free_assets(ff, fs, mode='free')[2]}", tlg=True)
            #
            if self.reverse:
                self.message_log(f"For Reverse cycle target return amount: {self.reverse_target_amount}",
                                 color=Style.B_WHITE)
            self.first_run = False
            self.debug_output()
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
                print(f"DELETE from t_order: {err}")
            self.connection_analytic.close()
        self.connection_analytic = None

    def suspend(self) -> None:
        print('Suspend')
        self.queue_to_db.put({'stop_signal': True})
        self.queue_to_tlg.put(STOP_TLG)
        self.connection_analytic.commit()
        self.connection_analytic.close()
        self.connection_analytic = None

    def unsuspend(self) -> None:
        print('Unsuspend')
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
                if STANDALONE:
                    raise SystemExit(1)
            _amount_first_grid = (_amount_first_grid * self.avg_rate) if self.cycle_buy else _amount_first_grid
            if _amount_first_grid > 80 * depo / 100:
                self.message_log(f"Recommended size of the first grid order {_amount_first_grid:f} too large for"
                                 f" a small deposit {self.deposit_second}", log_level=LogLevel.ERROR)
                if STANDALONE and self.first_run:
                    raise SystemExit(1)
            elif _amount_first_grid > 20 * depo / 100:
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
                if STANDALONE and self.first_run:
                    raise SystemExit(1)

    def save_init_assets(self, ff, fs):
        if self.reverse:
            self.initial_reverse_first = ff
            self.initial_reverse_second = fs
        else:
            self.initial_first = ff
            self.initial_second = fs

    def collect_assets(self) -> ():
        ff, fs, _x = self.get_free_assets(mode='free')
        tcm = self.get_trading_capability_manager()
        if ff >= f2d(tcm.min_qty):
            self.message_log(f"Sending {ff} {self.f_currency} to main account", color=Style.UNDERLINE, tlg=True)
            self.transfer_to_master(self.f_currency, any2str(ff))
        else:
            ff = f2d(0)
        if fs >= f2d(tcm.min_notional):
            self.message_log(f"Sending {fs} {self.s_currency} to main account", color=Style.UNDERLINE, tlg=True)
            self.transfer_to_master(self.s_currency, any2str(fs))
        else:
            fs = f2d(0)
        return ff, fs

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
            tr_arr.append(max(high[n] - low[n], abs(high[n] - close[n - 1]), abs(low[n] - close[n - 1])))
            n += 1
        _atr = statistics.geometric_mean(tr_arr)
        return _atr

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
        min_price = self.get_trading_capability_manager().get_minimal_price_change(0.0)
        # self.message_log(f"bollinger_band.min_price: {min_price}", log_level=LogLevel.DEBUG)
        min_price = min_price if min_price and not math.isinf(min_price) else 0.0
        bbb = max(bbb, min_price)
        # self.message_log(f"bollinger_band: tbb={tbb:f}, bbb={bbb:f}", log_level=LogLevel.DEBUG)
        return {'tbb': tbb, 'bbb': bbb}

    ##############################################################
    # strategy function
    ##############################################################

    def place_grid(self,
                   buy_side: bool,
                   depo: Decimal,
                   reverse_target_amount: Decimal,
                   allow_grid_shift: bool = True,
                   additional_grid: bool = False,
                   grid_update: bool = False,
                   init_calc_only: bool = False) -> None:
        if not init_calc_only:
            self.message_log(f"place_grid: buy_side: {buy_side}, depo: {depo},"
                             f" reverse_target_amount: {reverse_target_amount},"
                             f" allow_grid_shift: {allow_grid_shift},"
                             f" additional_grid: {additional_grid},"
                             f" grid_update: {grid_update}", log_level=LogLevel.DEBUG)
        self.grid_hold.clear()
        self.last_shift_time = None
        funds = self.get_buffered_funds()
        if buy_side:
            currency = self.s_currency
            fund = funds.get(currency, 0)
            fund = f2d(fund.available) if fund else Decimal('0.0')
        else:
            currency = self.f_currency
            fund = funds.get(currency, 0)
            fund = f2d(fund.available) if fund else Decimal('0.0')
        if depo <= fund:
            tcm = self.get_trading_capability_manager()
            last_executed_grid_price = float(self.avg_rate) if grid_update else 0
            if buy_side:
                _price = last_executed_grid_price or self.get_buffered_order_book().bids[0].price
                base_price = _price - PRICE_SHIFT * _price / 100
                amount_min = tcm.get_min_buy_amount(base_price)
            else:
                _price = last_executed_grid_price or self.get_buffered_order_book().asks[0].price
                base_price = _price + PRICE_SHIFT * _price / 100
                amount_min = tcm.get_min_sell_amount(base_price)
            min_delta = f2d(tcm.get_minimal_price_change(base_price))
            base_price_dec = f2d(tcm.round_price(base_price, RoundingType.ROUND))
            amount_min_dec = f2d(amount_min)
            # Adjust min_amount order quantity per fee
            _f, _s = self.fee_for_grid(amount_min_dec, amount_min_dec * self.avg_rate, by_market=True, print_info=False)
            if _f != amount_min_dec:
                amount_min_dec += amount_min_dec - _f
            elif _s != amount_min_dec * self.avg_rate:
                amount_min_dec += (amount_min_dec * self.avg_rate - _s) / self.avg_rate
            amount_min_dec = self.round_truncate(amount_min_dec, base=True, _rounding=ROUND_CEILING)
            #
            if ADAPTIVE_TRADE_CONDITION or self.reverse or additional_grid:
                try:
                    amount_first_grid = self.set_trade_conditions(buy_side,
                                                                  depo,
                                                                  base_price_dec,
                                                                  reverse_target_amount,
                                                                  min_delta,
                                                                  amount_min_dec,
                                                                  additional_grid=additional_grid,
                                                                  grid_update=grid_update)
                except Exception as ex:
                    self.message_log(f"Can't set trade conditions: {ex}", log_level=LogLevel.ERROR)
                    self.message_log(f"Can't set trade conditions: {traceback.print_exc()}", log_level=LogLevel.DEBUG)
                    return
            else:
                self.over_price = OVER_PRICE
                self.order_q = ORDER_Q
                amount_first_grid = amount_min_dec
            if self.order_q > 1:
                self.message_log(f"For{' Reverse' if self.reverse else ''} {'Buy' if buy_side else 'Sell'}"
                                 f" cycle{' will be' if init_calc_only else ''} set {self.order_q} orders"
                                 f" for {self.over_price:.4f}% over price", tlg=False)
            else:
                self.message_log(f"For{' Reverse' if self.reverse else ''} {'Buy' if buy_side else 'Sell'}"
                                 f" cycle set {self.order_q} order{' for additional grid' if additional_grid else ''}",
                                 tlg=False)
            if init_calc_only:
                self.init_warning(amount_first_grid)
                return
            #
            if self.order_q == 1:
                if self.reverse:
                    price = (depo / reverse_target_amount) if buy_side else (reverse_target_amount / depo)
                else:
                    price = base_price_dec
                price = f2d(tcm.round_price(float(price), RoundingType.ROUND))
                amount = self.round_truncate((depo / price) if buy_side else depo, base=True, _rounding=ROUND_FLOOR)
                orders = [(0, amount, price)]
            else:
                params = {'buy_side': buy_side,
                          'depo': depo,
                          'base_price': base_price_dec,
                          'amount_first_grid': amount_first_grid,
                          'min_delta': min_delta,
                          'amount_min': amount_min_dec}
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
                    waiting_order_id = self.place_limit_order(buy_side,
                                                              amount if STANDALONE else float(amount),
                                                              price if STANDALONE else float(price))
                    self.orders_init.append(waiting_order_id, buy_side, amount, price)
                else:
                    self.orders_hold.append(i, buy_side, amount, price)
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
                # TODO round to real assets scale
                self.message_log(f"Shift grid threshold: {self.shift_grid_threshold:.4f}")
            #
            self.start_after_shift = False
            if self.grid_update_started:
                self.grid_place_flag = None
                self.grid_update_started = None
        else:
            self.grid_hold = {'buy_side': buy_side,
                              'depo': depo,
                              'allow_grid_shift': allow_grid_shift,
                              'additional_grid': additional_grid,
                              'grid_update': grid_update,
                              'timestamp': time.time()}
            self.message_log(f"Hold grid for {'Buy' if buy_side else 'Sell'} cycle with {depo} {currency} depo."
                             f" Available funds is {fund} {currency}", tlg=False)
        if self.tp_hold_additional:
            self.message_log("Replace take profit order after place additional grid orders", tlg=True)
            self.tp_hold_additional = False
            self.place_profit_order()

    def calc_grid(self, over_price: Decimal, calc_avg_amount=True, **kwargs):
        """
        Calculate return average amount in second coin for grid orders with fixed initial parameters by default
        :param over_price:
        :param calc_avg_amount: False: Return Dict with prepared grid orders
        :param kwargs:
        :return:
        """
        buy_side = kwargs.get('buy_side')
        depo = kwargs.get('depo')
        base_price = kwargs.get('base_price')
        amount_first_grid = kwargs.get('amount_first_grid')
        min_delta = kwargs.get('min_delta')
        amount_min = kwargs.get('amount_min')
        #
        tcm = self.get_trading_capability_manager()
        # Decimal zone
        avg_rate = self.avg_rate or base_price
        try:
            max_price = f2d(tcm.get_max_sell_price(float(avg_rate)))
            min_price = f2d(tcm.get_min_buy_price(float(avg_rate)))
        except AttributeError:
            max_price = avg_rate * f2d(5)
            min_price = avg_rate * f2d(0.2)
        #
        delta_price = over_price * base_price / (100 * (self.order_q - 1))
        price_prev = base_price
        avg_amount = f2d(0)
        total_grid_amount_f = f2d(0)
        total_grid_amount_s = f2d(0)
        depo_i = f2d(0)
        rounding = ROUND_CEILING
        last_order_pass = False
        price_k = 1
        amount_last_grid = f2d(0)
        orders = []
        for i in range(self.order_q):
            if LINEAR_GRID_K >= 0:
                price_k = f2d(1 - math.log(self.order_q - i, self.order_q + LINEAR_GRID_K))
            if buy_side:
                price = base_price - i * delta_price * price_k
            else:
                price = base_price + i * delta_price * price_k
            price = f2d(tcm.round_price(float(price), RoundingType.ROUND))
            if buy_side:
                if i and price_prev - price < min_delta:
                    price = price_prev - min_delta
            else:
                if i and price - price_prev < min_delta:
                    price = price_prev + min_delta
            if buy_side:
                price = max(price, min_price)
            else:
                price = min(price, max_price)
            price_prev = price
            if i == 0:
                amount_0 = depo * self.martin ** i * (self.martin - 1) / (self.martin ** self.order_q - 1)
                amount = max(amount_0, amount_first_grid * (price if buy_side else 1))
                depo_i = depo - amount
                # print(f"calc_grid 0: {i}, amount: {amount}, price: {price}, depo: {depo}, depo_i: {depo_i}")
            elif i < self.order_q - 1:
                amount = depo_i * self.martin ** i * (self.martin - 1) / (self.martin ** self.order_q - 1)
                # print(f"calc_grid 1: {i}, amount: {amount}, price: {price}")
            else:
                amount = amount_last_grid
                rounding = ROUND_FLOOR
                # print(f"calc_grid last: {i}, amount: {amount}, price: {price}")
            if buy_side:
                amount /= price
            amount = self.round_truncate(amount, base=True, _rounding=rounding)
            total_grid_amount_f += amount
            total_grid_amount_s += amount * price
            # Check last order volume
            if i == self.order_q - 2:
                amount_last_grid = depo - (total_grid_amount_s if buy_side else total_grid_amount_f)
                if amount_last_grid < amount_min * (price if buy_side else 1):
                    # Skip last order
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
            # print(f"calc_grid: {i}, amount: {amount}, price: {price}")
            if last_order_pass:
                total_grid_amount_f += amount
                total_grid_amount_s += amount * price
                break
        # print(f"calc_grid: total_grid_amount_f: {total_grid_amount_f}, total_grid_amount_s: {total_grid_amount_s}")
        # print(f"calc_grid: order_q: {self.order_q}, over_price: {float(over_price):f}, avg_amount: {avg_amount}")
        if calc_avg_amount:
            return avg_amount
        res = {
            'total_grid_amount_f': total_grid_amount_f,
            'total_grid_amount_s': total_grid_amount_s,
            'orders': orders
        }
        return res

    def grid_update(self, frequency: str):
        try:
            bb = self.bollinger_band(BB_CANDLE_SIZE_IN_MINUTES, BB_NUMBER_OF_CANDLES)
        except Exception as ex:
            self.message_log(f"Can't get BB in grid update: {ex}", log_level=LogLevel.INFO)
        else:
            do_it = False
            if self.orders_hold:
                last_price = float(self.orders_hold.get_last()[2])
            else:
                last_price = float(self.orders_grid.get_last()[2])
            predicted_price = bb.get('bbb') if self.cycle_buy else bb.get('tbb')
            if self.cycle_buy:
                delta = 100 * (last_price - predicted_price) / last_price
            else:
                delta = 100 * (predicted_price - last_price) / last_price
            depo_remaining = ((self.orders_grid.sum_amount(self.cycle_buy) +
                               self.orders_hold.sum_amount(self.cycle_buy)) /
                              (self.deposit_second if self.cycle_buy else self.deposit_first))
            depo_check = depo_remaining >= f2d(0.8)
            if frequency == 'hi' and delta > 0:
                do_it = depo_check and delta > 0.5
            elif frequency == 'mid' and delta > 0:
                do_it = depo_check and delta > 0.25
            elif frequency == 'low':
                if delta > 0:
                    do_it = depo_check and delta > 0.12
                else:
                    do_it = depo_remaining >= f2d(0.2) and -1 * delta > 3

            if do_it:
                self.message_log(f"Update grid orders, frequency: {frequency},"
                                 f" BB limit difference: {delta:.2f}%", tlg=True)
                self.grid_update_started = True
                self.cancel_grid()

    def place_profit_order(self, by_market: bool = False) -> None:
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
                    fund = f2d(fund.available) if fund else Decimal('0.0')
                else:
                    fund = funds.get(self.f_currency, 0)
                    fund = f2d(fund.available) if fund else Decimal('0.0')
                if buy_side and amount * price > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side,
                                          'amount': amount * price,
                                          'by_market': by_market,
                                          'timestamp': time.time()}
                    self.message_log(f"Hold take profit order for Buy {amount} {self.f_currency} by {price},"
                                     f" wait {amount * price} {self.s_currency}, exist: {fund}")
                elif not buy_side and amount > fund:
                    # Save take profit order and wait update balance
                    self.tp_order_hold = {'buy_side': buy_side,
                                          'amount': amount,
                                          'by_market': by_market,
                                          'timestamp': time.time()}
                    self.message_log(f"Hold take profit order for Sell {amount} {self.f_currency}"
                                     f" by {price}, exist {fund}")
                else:
                    # Create take profit order
                    self.message_log(f"Create {'Buy' if buy_side else 'Sell'} take profit order,"
                                     f" vlm: {amount}, price: {price}, profit: {profit}%")
                    self.tp_target = target
                    if not STANDALONE:
                        _amount = float(amount)
                        _price = float(price)
                        tcm = self.get_trading_capability_manager()
                        if not tcm.is_limit_order_valid(buy_side, _amount, _price):
                            _amount = tcm.round_amount(_amount, RoundingType.FLOOR)
                            if buy_side:
                                _price = tcm.round_price(_price, RoundingType.FLOOR)
                            else:
                                _price = tcm.round_price(_price, RoundingType.CEIL)
                            amount = f2d(_amount)
                            price = f2d(_price)
                            self.message_log(f"Rounded amount: {amount}, price: {price}")
                    self.tp_order = (buy_side, amount, price)
                    check = (len(self.orders_grid) + len(self.orders_hold)) > 2
                    self.tp_wait_id = self.place_limit_order_check(buy_side, amount, price, check=check)

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
        step_size = f2d(tcm.get_minimal_amount_change(float(amount_min)))
        self.message_log(f"set_trade_conditions: buy_side: {buy_side}, depo: {float(depo):f}, base_price: {base_price},"
                         f" reverse_target_amount: {reverse_target_amount}, amount_min: {amount_min},"
                         f" step_size: {step_size}, delta_min: {delta_min}", LogLevel.DEBUG)
        depo_c = (depo / base_price) if buy_side else depo
        if not additional_grid and not grid_update and not GRID_ONLY and 0 < PROFIT_MAX < 100:
            try:
                profit_max = min(PROFIT_MAX, max(PROFIT, f2d(100 * self.atr() / self.get_buffered_ticker().last_price)))
            except statistics.StatisticsError as ex:
                self.message_log(f"Can't get ATR value: {ex}, use default PROFIT_MAX value", LogLevel.WARNING)
                profit_max = PROFIT_MAX
            self.message_log(f"Profit max for first order volume is: {profit_max}", LogLevel.DEBUG)
            k_m = 1 - profit_max / 100
            amount_first_grid = max(amount_min, (step_size * base_price / ((1 / k_m) - 1)) / base_price)
            # For Bitfinex test accounts correction
            if amount_first_grid >= f2d(tcm.get_max_sell_amount(0)) or amount_first_grid >= depo_c:
                amount_first_grid /= ORDER_Q
            amount_first_grid = self.round_truncate(amount_first_grid, base=True, _rounding=ROUND_CEILING)
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
                over_price = 100 * (base_price - f2d(bbb)) / base_price
            else:
                tbb = bb.get('tbb')
                over_price = 100 * (f2d(tbb) - base_price) / base_price
        self.over_price = max(over_price, OVER_PRICE)
        # Adapt grid orders quantity for current over price
        order_q = int(self.over_price * ORDER_Q / OVER_PRICE)
        depo_c = (depo / base_price) if buy_side else depo
        amnt_2 = amount_min * self.martin
        q_max = int(math.log(1 + (depo_c - amount_first_grid) * self.martin * (self.martin - 1) / amnt_2, self.martin))
        self.message_log(f"set_trade_conditions: depo: {float(depo):f}, order_q: {order_q},"
                         f" amount_first_grid: {amount_first_grid:f}, amount_2: {amnt_2:f},"
                         f" q_max: {q_max}, coarse overprice: {float(self.over_price):f}", LogLevel.DEBUG)
        while q_max > 3 or (GRID_ONLY and q_max > 1):
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
        # Correction over_price after change quantity of orders
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
                tbb = f2d(bb.get('tbb', 0))
                bbb = f2d(bb.get('bbb', 0))
        if tbb and bbb:
            if self.cycle_buy:
                profit = 100 * (tbb * amount - self.tp_amount) / self.tp_amount
            else:
                profit = 100 * (amount / bbb - self.tp_amount) / self.tp_amount
            profit = min(max(profit, PROFIT + fee), PROFIT_MAX)
        else:
            profit = PROFIT + fee
        return Decimal(profit).quantize(Decimal("1.0123"), rounding=ROUND_CEILING)

    def calc_profit_order(self, buy_side: bool, by_market: bool = False) -> Dict[str, Decimal]:
        """
        Calculation based on amount value
        :param buy_side: for take profit order, inverse to current cycle
        :param by_market:
        :return:
        """
        self.message_log(f"calc_profit_order: buy_side: {buy_side}, by_market: {by_market}", LogLevel.DEBUG)
        tcm = self.get_trading_capability_manager()
        step_size_f = f2d(tcm.get_minimal_amount_change(0.0))
        if buy_side:
            # Calculate target amount for first
            self.tp_amount = self.sum_amount_first
            profit = self.set_profit(self.sum_amount_second, by_market)
            target_amount_first = self.sum_amount_first + profit * self.sum_amount_first / 100
            target_amount_first = self.round_truncate(target_amount_first, base=True, _rounding=ROUND_FLOOR)
            if target_amount_first - self.tp_amount < step_size_f:
                target_amount_first = self.tp_amount + step_size_f
            amount = target = target_amount_first
            # Calculate depo amount in second
            amount_s = self.round_truncate(self.sum_amount_second, base=False, _rounding=ROUND_FLOOR)
            price = f2d(tcm.round_price(float(amount_s / target_amount_first), RoundingType.FLOOR))
        else:
            step_size_s = self.round_truncate((step_size_f * self.avg_rate), base=False, _rounding=ROUND_CEILING)
            # Calculate target amount for second
            self.tp_amount = self.sum_amount_second
            profit = self.set_profit(self.sum_amount_first, by_market)
            target_amount_second = self.sum_amount_second + profit * self.sum_amount_second / 100
            target_amount_second = self.round_truncate(target_amount_second, base=False, _rounding=ROUND_CEILING)
            if target_amount_second - self.tp_amount < step_size_s:
                target_amount_second = self.tp_amount + step_size_s
            # Calculate depo amount in first
            amount = self.round_truncate(self.sum_amount_first, base=True, _rounding=ROUND_FLOOR)
            price = f2d(tcm.round_price(float(target_amount_second / amount), RoundingType.CEIL))
            target = amount * price
        self.tp_init = (self.sum_amount_first, self.sum_amount_second)
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
        self.message_log(f"over_price coarse: {over_price_coarse:.6f}, max_err: {max_err}", log_level=LogLevel.DEBUG)
        if self.order_q > 1 and over_price_coarse > 0:
            # Fine calculate over_price for target return amount
            params = {'buy_side': buy_side,
                      'depo': depo,
                      'base_price': base_price,
                      'amount_first_grid': amount_first_grid,
                      'min_delta': min_delta,
                      'amount_min': amount_min}
            over_price = solve(self.calc_grid, reverse_target_amount, over_price_coarse, max_err, **params)
            if over_price == 0:
                self.message_log("Can't calculate over price for reverse cycle,"
                                 " use previous or over_price_coarse * 3", log_level=LogLevel.ERROR)
                over_price = over_price_previous or 3 * over_price_coarse
        else:
            over_price = over_price_coarse
        return over_price

    def start_process(self):
        # Init analytic
        self.connection_analytic = self.connection_analytic or sqlite3.connect(DB_FILE,
                                                                               check_same_thread=False,
                                                                               timeout=10)
        # Create processes for save to .db and send Telegram message
        self.pr_db = Thread(target=save_to_db, args=(self.queue_to_db,))
        self.pr_tlg = Thread(target=telegram, args=(self.queue_to_tlg, self.tlg_header.split('.')[0],))
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

    def round_fee(self, fee, amount, base):
        return self.round_truncate(fee * amount / 100, base=base, fee=True, _rounding=ROUND_CEILING)

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
                    message = f"For grid order First - fee: {amount_first}"
                else:
                    amount_first += self.round_fee(fee, amount_first, base=True)
                    message = f"For grid order First + fee: {amount_first}"
            else:
                if self.cycle_buy:
                    if FEE_SECOND:
                        amount_second += self.round_fee(fee, amount_second, base=False)
                        message = f"For grid order Second + fee: {amount_second}"
                    else:
                        amount_first -= self.round_fee(fee, amount_first, base=True)
                        message = f"For grid order First - fee: {amount_first}"
                else:
                    amount_second -= self.round_fee(fee, amount_second, base=False)
                    message = f"For grid order Second - fee: {amount_second}"
        if print_info and message:
            self.message_log(message, log_level=LogLevel.DEBUG)
        return self.round_truncate(amount_first, base=True), self.round_truncate(amount_second, base=False)

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
            profit_reverse = profit_second if self.reverse and self.cycle_buy_count % 2 == 0 else Decimal('0')
            profit_second -= profit_reverse
            self.profit_second += profit_second
            self.part_profit_second = Decimal('0')
            self.message_log(f"Cycle profit second {self.profit_second} + {profit_reverse}")
        else:
            profit_first = self.round_truncate(amount_first_fee - self.tp_amount, base=True)
            profit_reverse = profit_first if self.reverse and self.cycle_sell_count % 2 == 0 else Decimal('0')
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
                             log_level=LogLevel.INFO, color=Style.MAGENTA)
            self.sum_amount_first -= self.tp_init[0]
            self.sum_amount_second -= self.tp_init[1]
            self.message_log(f"Sum_amount_first: {self.sum_amount_first}, Sum_amount_second: {self.sum_amount_second}",
                             log_level=LogLevel.INFO, color=Style.MAGENTA)
            self.tp_was_filled = ()
            # Return depo in turnover without loss
            tcm = self.get_trading_capability_manager()
            if self.cycle_buy:
                min_trade_amount = tcm.get_min_buy_amount(float(self.avg_rate))
                amount = self.tp_init[1]
                if self.reverse:
                    reverse_target_amount = self.reverse_target_amount * self.tp_init[0] / self.reverse_init_amount
                else:
                    reverse_target_amount = self.tp_init[0] + (FEE_MAKER * 2 + PROFIT) * self.tp_init[0] / 100
            else:
                min_trade_amount = tcm.get_min_sell_amount(float(self.avg_rate))
                amount = self.tp_init[0]
                if self.reverse:
                    reverse_target_amount = self.reverse_target_amount * self.tp_init[1] / self.reverse_init_amount
                else:
                    reverse_target_amount = self.tp_init[1] + (FEE_MAKER * 2 + PROFIT) * self.tp_init[1] / 100
            self.message_log(f"Min trade amount is: {min_trade_amount}")
            self.debug_output()
            self.message_log(f"For additional grid amount: {amount}, reverse_target_amount: {reverse_target_amount}",
                             tlg=True)
            if float(amount) > min_trade_amount:
                self.message_log("Place additional grid orders and replace TP", tlg=True)
                self.tp_hold_additional = True
                self.place_grid(self.cycle_buy,
                                amount,
                                reverse_target_amount,
                                allow_grid_shift=False,
                                additional_grid=True)
                return
            self.message_log("Too small for trade, transfer filled TP amount to the next cycle", tlg=True)
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
            self.cancel_grid()
        else:
            self.message_log("Restart after filling take profit order", tlg=False)
        self.debug_output()
        self.restart = True
        self.sum_amount_first = transfer_sum_amount_first
        self.sum_amount_second = transfer_sum_amount_second
        self.part_amount.clear()
        self.correction_amount_first = Decimal('0')
        self.correction_amount_second = Decimal('0')
        self.tp_part_amount_first = Decimal('0')
        self.tp_part_amount_second = Decimal('0')
        self.start(profit_f, profit_s)

    def reverse_after_grid_ending(self):
        self.message_log("reverse_after_grid_ending:", log_level=LogLevel.DEBUG)
        self.debug_output()
        profit_f = f2d(0)
        profit_s = f2d(0)
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
            self.reverse_target_amount = Decimal('0')
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
            self.start_reverse_time = time.time()
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
            self.debug_output()
            self.tp_part_amount_first = Decimal('0')
            self.tp_part_amount_second = Decimal('0')
            self.start(profit_f, profit_s)

    def place_grid_part(self) -> None:
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
                waiting_order_id = self.place_limit_order_check(i['buy'], i['amount'], i['price'], check=True)
                self.orders_init.append(waiting_order_id, i['buy'], i['amount'], i['price'])
                k += 1
            del self.orders_hold.orders_list[:k]

    def grid_only_stop(self) -> None:
        tcm = self.get_trading_capability_manager()
        avg_rate = tcm.round_price(float(self.sum_amount_second / self.sum_amount_first), RoundingType.FLOOR)
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
        self.sum_amount_first = Decimal('0')
        self.sum_amount_second = Decimal('0')
        if USE_ALL_FUND:
            self.grid_only_restart = True
            self.message_log("Waiting funding for convert", color=Style.B_WHITE)
            return
        self.command = 'stop'

    def grid_handler(self,
                     _amount_first=None,
                     _amount_second=None,
                     by_market: bool = False,
                     after_full_fill: bool = True,
                     order_id=None) -> None:
        """
        Handler after filling grid order
        """
        if after_full_fill and _amount_first:
            # Calculate trade amount with Fee
            amount_first_fee, amount_second_fee = self.fee_for_grid(_amount_first, _amount_second, by_market)
            # Get partially filled amount
            if order_id:
                part_amount = self.part_amount.pop(order_id, (Decimal('0'), Decimal('0')))
            else:
                part_amount = (Decimal('0'), Decimal('0'))
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
                    self.cancel_order(self.tp_order_id)
                return
            if self.tp_wait_id:
                # Wait tp order and cancel in on_cancel_order_success and restart
                self.tp_cancel_from_grid_handler = True
                return
            if GRID_ONLY:
                self.shift_grid_threshold = None
                self.grid_only_stop()
            elif self.tp_part_amount_first or self.correction_amount_first:
                self.message_log("grid_handler: No grid orders after part filled TP, converse TP to grid", tlg=True)
                if self.tp_part_amount_first:
                    # Correction sum_amount
                    self.message_log(f"Before Correction: Sum_amount_first: {self.sum_amount_first},"
                                     f" Sum_amount_second: {self.sum_amount_second}",
                                     log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                    self.sum_amount_first -= self.tp_part_amount_first
                    self.sum_amount_second -= self.tp_part_amount_second
                    self.message_log(f"Sum_amount_first: {self.sum_amount_first},"
                                     f" Sum_amount_second: {self.sum_amount_second}",
                                     log_level=LogLevel.DEBUG, color=Style.MAGENTA)
                _amount_f = self.tp_part_amount_first + self.correction_amount_first
                _amount_s = self.tp_part_amount_second + self.correction_amount_second
                self.correction_amount_first = Decimal('0')
                self.correction_amount_second = Decimal('0')
                self.tp_part_amount_first = Decimal('0')
                self.tp_part_amount_second = Decimal('0')
                self.message_log(f"Saved TP part amount was: first: {_amount_f}, second: {_amount_s}",
                                 log_level=LogLevel.DEBUG)
                tcm = self.get_trading_capability_manager()
                # Return depo in turnover without loss
                if self.cycle_buy:
                    min_trade_amount = tcm.get_min_buy_amount(float(self.avg_rate))
                    amount = _amount_s
                    if self.reverse:
                        reverse_target_amount = self.reverse_target_amount * _amount_f / self.reverse_init_amount
                    else:
                        reverse_target_amount = _amount_f + (FEE_MAKER * 2 + PROFIT) * _amount_f / 100
                    first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin**GRID_MAX_COUNT)
                    first_order_vlm /= self.avg_rate
                else:
                    min_trade_amount = tcm.get_min_sell_amount(float(self.avg_rate))
                    amount = _amount_f
                    if self.reverse:
                        reverse_target_amount = self.reverse_target_amount * _amount_s / self.reverse_init_amount
                    else:
                        reverse_target_amount = _amount_s + (FEE_MAKER * 2 + PROFIT) * _amount_s / 100
                    first_order_vlm = amount * 1 * (1 - self.martin) / (1 - self.martin**GRID_MAX_COUNT)
                self.message_log(f"Min trade amount is: {min_trade_amount}")
                self.debug_output()
                self.message_log(f"For additional grid amount: {amount},"
                                 f" reverse_target_amount: {reverse_target_amount}", tlg=True)
                if float(first_order_vlm) > min_trade_amount:
                    self.message_log("Place additional grid orders", tlg=True)
                    self.place_grid(self.cycle_buy, amount, reverse_target_amount, allow_grid_shift=False)
                    return
                if float(amount) > min_trade_amount:
                    self.message_log(f"Too small amount for place additional grid,"
                                     f" add grid order for {'Buy' if self.cycle_buy else 'Sell'}"
                                     f" {reverse_target_amount} by {amount / reverse_target_amount:f}")
                    waiting_order_id = self.place_limit_order_check(self.cycle_buy, reverse_target_amount, amount / reverse_target_amount)
                    self.orders_init.append(waiting_order_id, self.cycle_buy, reverse_target_amount,
                                            amount / reverse_target_amount)
                self.place_profit_order(by_market)
            elif self.tp_was_filled:
                self.message_log("grid_handler: Was filled TP and all grid orders, converse TP to grid", tlg=True)
                self.after_filled_tp(one_else_grid=True)
            else:
                # Ended grid order, calculate depo and Reverse
                self.reverse_after_grid_ending()
        else:
            if self.orders_save:
                self.grid_remove = False if self.grid_order_canceled else None
                self.start_hold = False
                self.message_log("grid_handler: Restore deleted and unplaced grid orders")
                self.orders_hold.orders_list.extend(self.orders_save)
                # Sort restored hold orders
                self.orders_hold.sort(self.cycle_buy)
                self.orders_save.orders_list.clear()
                self.order_q_placed = False
            if after_full_fill and self.orders_hold and self.order_q_placed:
                # PLace one hold grid order and remove it from hold list
                _buy, _amount, _price = self.orders_hold.get_first()
                check = (len(self.orders_grid) + len(self.orders_hold)) <= 2
                waiting_order_id = self.place_limit_order_check(_buy, _amount, _price, check=check)
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
                self.order_q_placed = None
                sum_amount = self.orders_save.sum_amount(self.cycle_buy) if self.grid_update_started else Decimal('0.0')
                self.orders_save.orders_list.clear()
                if self.tp_was_filled:
                    self.grid_update_started = None
                    self.after_filled_tp(one_else_grid=False)
                elif self.grid_update_started:
                    self.message_log(f"Start update grid orders, depo: {sum_amount}", log_level=LogLevel.DEBUG)
                    self.place_grid(self.cycle_buy,
                                    sum_amount,
                                    self.reverse_target_amount,
                                    allow_grid_shift=False,
                                    grid_update=True)
                else:
                    self.grid_update_started = None
                    self.start()
        else:
            self.grid_remove = None

    def round_truncate(self, _x: Decimal, base: bool, fee: bool = False, _rounding=ROUND_FLOOR) -> Decimal:
        if fee:
            round_pattern = "1.01234567"
        else:
            round_pattern = self.round_base if base else self.round_quote
        xr = _x.quantize(Decimal(round_pattern), rounding=_rounding)
        return xr

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
        if self.grid_order_canceled in strategy_orders_id:
            strategy_orders_id.remove(self.grid_order_canceled)
        diff_id = list(set(strategy_orders_id).difference(market_orders_id))
        if diff_id:
            self.message_log(f"Orders not present on exchange: {diff_id}", tlg=True)
            if diff_id.count(self.tp_order_id):
                diff_id.remove(self.tp_order_id)
                amount_first = self.tp_order[1]
                amount_second = self.tp_order[1] * self.tp_order[2]
                self.tp_was_filled = (amount_first, amount_second, True)
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
                    amount_first += _amount
                    amount_second += _amount * _price
                self.message_log(f"Grid amount: First: {amount_first}, Second: {amount_second}")
                self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)
            elif self.tp_was_filled:
                self.cancel_grid()

    def check_min_amount(self, for_tp=True) -> bool:
        res = False
        if self.avg_rate:
            tcm = self.get_trading_capability_manager()
            if self.cycle_buy:
                min_trade_amount = f2d(tcm.get_min_sell_amount(float(self.avg_rate)))
                amount = self.sum_amount_first if for_tp else (self.deposit_second / self.avg_rate)
                amount = self.round_truncate(amount, base=True)
            else:
                min_trade_amount = f2d(tcm.get_min_buy_amount(float(self.avg_rate)))
                amount = (self.sum_amount_second / self.avg_rate) if for_tp else self.deposit_first
                amount = self.round_truncate(amount, base=True)
            if amount >= min_trade_amount:
                res = True
        return res

    def place_limit_order_check(self, buy: bool, amount: Decimal, price: Decimal, check=False) -> int:
        """
        Before place limit order check trade conditions and correct price
        """
        _price = float(price)
        if check:
            order_book = self.get_buffered_order_book()
            if buy and order_book.bids:
                price = f2d(min(_price, order_book.bids[0].price))
            elif not buy and order_book.asks:
                price = f2d(max(_price, order_book.asks[0].price))

        waiting_order_id = self.place_limit_order(buy,
                                                  amount if STANDALONE else float(amount),
                                                  price if STANDALONE else float(price))
        if check and _price != float(price):
            self.message_log(f"For order {waiting_order_id} price was updated from {_price} to {price}",
                             log_level=LogLevel.WARNING)
        return waiting_order_id

    def get_free_assets(self, ff: Decimal = None, fs: Decimal = None, mode: str = 'total') -> ():
        """
        Get free asset for current trade pair
        :param fs:
        :param ff:
        :param mode: 'total', 'free', 'reserved'
        :return: (ff, fs, free_asset: str)
        """
        if ff is None or fs is None:
            funds = self.get_buffered_funds()
            _ff = funds.get(self.f_currency, 0)
            _fs = funds.get(self.s_currency, 0)
            ff = Decimal('0')
            fs = Decimal('0')
            if _ff and _fs:
                if mode == 'total':
                    ff = f2d(_ff.total_for_currency)
                    fs = f2d(_fs.total_for_currency)
                elif mode == 'free':
                    ff = f2d(_ff.available)
                    fs = f2d(_fs.available)
                elif mode == 'reserved':
                    ff = f2d(_ff.reserved)
                    fs = f2d(_fs.reserved)
        #
        if mode == 'free':
            if self.cycle_buy:
                fs = (self.initial_reverse_second if self.reverse else self.initial_second) - self.deposit_second
            else:
                ff = (self.initial_reverse_first if self.reverse else self.initial_first) - self.deposit_first
        ff = self.round_truncate(ff, base=True)
        fs = self.round_truncate(fs, base=False)
        assets = f"{mode.capitalize()}: First: {ff}, Second: {fs}"
        return ff, fs, assets

    ##############################################################
    # public data update methods
    ##############################################################
    def on_new_ticker(self, ticker: Ticker) -> None:
        # print(f"on_new_ticker:ticker.last_price: {ticker.last_price}")
        self.last_ticker_update = int(time.time())
        if (self.shift_grid_threshold and self.last_shift_time and time.time() - self.last_shift_time > SHIFT_GRID_DELAY
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
            self.cancel_grid()

    def on_new_order_book(self, order_book: OrderBook) -> None:
        # print(f"on_new_order_book: max_bids: {order_book.bids[0].price}, min_asks: {order_book.asks[0].price}")
        pass
    ##############################################################
    # private update methods
    ##############################################################

    def on_balance_update(self, balance: Dict) -> None:
        asset = balance['asset']
        delta = Decimal(balance['balance_delta'])
        if delta > 0:
            delta = self.round_truncate(delta, bool(asset == self.f_currency), _rounding=ROUND_FLOOR)
        else:
            delta = self.round_truncate(delta, bool(asset == self.f_currency), _rounding=ROUND_CEILING)
        #
        if self.cycle_buy:
            if asset == self.s_currency:
                if self.reverse:
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
                if self.reverse:
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
        if (self.grid_only_restart or (GRID_ONLY and USE_ALL_FUND)) and delta > 0:
            self.restart = True
            self.grid_only_restart = None
            self.grid_remove = None
            self.cancel_grid()

    def on_new_funds(self, funds: Dict[str, FundsEntry]) -> None:
        # print(f"on_new_funds.funds: {funds}")
        ff = funds.get(self.f_currency, 0)
        fs = funds.get(self.s_currency, 0)
        if self.wait_refunding_for_start:
            ff = f2d(ff.total_for_currency) if ff else Decimal('0.0')
            fs = f2d(fs.total_for_currency) if fs else Decimal('0.0')
            if self.cycle_buy:
                go_trade = fs >= self.initial_reverse_second if self.reverse else self.initial_second
            else:
                go_trade = ff >= self.initial_reverse_first if self.reverse else self.initial_first
            if go_trade:
                self.message_log("Start after on_new_funds())")
                self.start()
                return
        if self.tp_order_hold:
            if self.tp_order_hold['buy_side']:
                available_fund = f2d(fs.available) if fs else Decimal('0.0')
            else:
                available_fund = f2d(ff.available) if ff else Decimal('0.0')
            if available_fund >= self.tp_order_hold['amount']:
                self.place_profit_order(by_market=self.tp_order_hold['by_market'])
                return
        if self.grid_hold:
            if self.grid_hold['buy_side']:
                available_fund = f2d(fs.available) if fs else Decimal('0.0')
            else:
                available_fund = f2d(ff.available) if ff else Decimal('0.0')
            if available_fund >= self.grid_hold['depo']:
                self.place_grid(self.grid_hold['buy_side'],
                                self.grid_hold['depo'],
                                self.reverse_target_amount,
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
                    amount_first = f2d(i.amount)
                    amount_second = f2d(i.amount) * f2d(i.price)
                    self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
                else:
                    self.message_log(f"No records for {update.original_order.id}", log_level=LogLevel.WARNING)
            else:
                for i in result_trades:
                    # Calculate sum trade amount for both currency
                    amount_first += f2d(i.amount)
                    amount_second += f2d(i.amount) * f2d(i.price)
                    self.message_log(f"trade id={i.id}, first: {i.amount}, price: {i.price}", log_level=LogLevel.DEBUG)
            # Retreat of courses
            if amount_first == 0:
                self.message_log(f"No amount for {update.original_order.id}", log_level=LogLevel.WARNING)
                return
            self.avg_rate = amount_second / amount_first
            self.message_log(f"Executed amount: First: {amount_first},"
                             f" Second: {amount_second},"
                             f" price: {self.avg_rate:.6f}")
            if update.status in (OrderUpdate.FILLED, OrderUpdate.ADAPTED_AND_FILLED):
                if not GRID_ONLY:
                    self.shift_grid_threshold = None
                if self.orders_grid.exist(update.original_order.id):
                    # Remove grid order with =id from order list
                    self.orders_grid.remove(update.original_order.id)
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
                        self.reverse_hold = False
                        self.cycle_time_reverse = None
                        self.initial_reverse_first = Decimal('0')
                        self.initial_reverse_second = Decimal('0')
                        self.message_log("Cancel hold reverse cycle", color=Style.B_WHITE, tlg=True)
                    self.tp_part_amount_first = Decimal('0')
                    self.tp_part_amount_second = Decimal('0')
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
                        self.grid_remove = True
                        self.cancel_grid()
                else:
                    self.message_log('Wild order, do not know it', tlg=True)
            elif update.status == OrderUpdate.PARTIALLY_FILLED:
                if self.tp_order_id == update.original_order.id:
                    self.message_log("Take profit partially filled", color=Style.B_WHITE)
                    amount_first_fee, amount_second_fee = self.fee_for_tp(amount_first, amount_second)
                    # Calculate profit for filled part TP
                    _profit_first = Decimal('0')
                    _profit_second = Decimal('0')
                    if self.cycle_buy:
                        _x, target_fee = self.fee_for_tp(Decimal('0'), self.tp_target, log_output=False)
                        _profit_second = self.round_truncate(((target_fee - self.tp_amount) * amount_second_fee /
                                                              target_fee), base=False)
                        self.part_profit_second += _profit_second
                        self.message_log(f"Part profit second {self.part_profit_second}", log_level=LogLevel.DEBUG)
                    else:
                        target_fee, _x = self.fee_for_tp(self.tp_target, Decimal('0'), log_output=False)
                        _profit_first = self.round_truncate(((target_fee - self.tp_amount) * amount_first_fee /
                                                             target_fee), base=True)
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
                            self.reverse_target_amount -= amount_second_fee
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
                            self.reverse_target_amount -= amount_first_fee
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
                    part_amount_first, part_amount_second = self.part_amount.pop(update.original_order.id,
                                                                                 (Decimal('0'), Decimal('0')))
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
                            self.last_shift_time = time.time() + 2 * SHIFT_GRID_DELAY
                            self.message_log("Partially trade too small, ignore", color=Style.B_WHITE)

    def on_place_order_success(self, place_order_id: int, order: Order) -> None:
        # print(f"on_place_order_success.place_order_id: {place_order_id}")
        if order.amount > order.received_amount > 0:
            self.message_log(f"Order {place_order_id} was partially filled", color=Style.B_WHITE)
            self.shift_grid_threshold = None
        if order.remaining_amount == 0.0:
            self.shift_grid_threshold = None
            # Get actual parameter of last trade order
            market_order = self.get_buffered_completed_trades()
            amount_first = Decimal('0')
            amount_second = Decimal('0')
            self.message_log(f"Order {place_order_id} executed by market", color=Style.B_WHITE)
            for o in market_order:
                if o.order_id == order.id:
                    amount_first += f2d(o.amount)
                    amount_second += f2d(o.amount) * f2d(o.price)
            if not amount_first:
                amount_first += f2d(order.amount)
                amount_second += f2d(order.amount) * f2d(order.price)
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
                self.tp_was_filled = (amount_first, amount_second, True)
                if self.tp_hold or self.tp_cancel_from_grid_handler:
                    self.tp_cancel_from_grid_handler = False
                    self.tp_hold = False
                    # After place but before accept TP was filled some grid
                    self.after_filled_tp(one_else_grid=True)
                else:
                    self.grid_remove = True
                    self.cancel_grid()
            else:
                self.message_log(f"Did not have waiting order id for {place_order_id}", LogLevel.ERROR,
                                 color=Style.B_RED)
        else:
            if self.orders_init.exist(place_order_id):
                self.orders_grid.append(order.id, order.buy, f2d(order.amount), f2d(order.price))
                self.orders_grid.sort(self.cycle_buy)
                '''
                self.message_log(f"on_place_order_success.orders_grid", log_level=LogLevel.DEBUG)
                for i in self.orders_grid.orders_list:
                    self.message_log(f"orders_grid: {i}", log_level=LogLevel.DEBUG)
                '''
                self.orders_init.remove(place_order_id)
                # self.message_log(f"Waiting order count is: {len(self.orders_init)}, hold: {len(self.orders_hold)}")
                if not self.orders_init:
                    self.last_shift_time = time.time()
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
                        self.place_grid_part()
            else:
                self.message_log(F"Did not have waiting order id for {place_order_id}", LogLevel.ERROR)

    def on_place_order_error_string(self, place_order_id: int, error: str) -> None:
        # Check all orders on exchange if exists required
        self.message_log(f"On place order {place_order_id} error: {error}", LogLevel.ERROR, tlg=True)
        open_orders = self.get_buffered_open_orders(True)  # lgtm [py/call/wrong-arguments]
        order = None
        if self.orders_init.exist(place_order_id):
            order = self.orders_init.find_order(open_orders, place_order_id)
        elif place_order_id == self.tp_wait_id:
            for k, o in enumerate(open_orders):
                if o.buy == self.tp_order[0] and o.amount == float(self.tp_order[1]) and o.price == float(self.tp_order[2]):
                    order = open_orders[k]
        if order:
            self.message_log(f"Order {place_order_id} placed", tlg=True)
            self.on_place_order_success(place_order_id, order)
        elif 'FAILED_PRECONDITION' not in error:
            self.message_log(f"Trying place order {place_order_id} one more time", tlg=True)
            if self.orders_init.exist(place_order_id):
                _buy, _amount, _price = self.orders_init.get_by_id(place_order_id)
                self.orders_init.remove(place_order_id)
                waiting_order_id = self.place_limit_order_check(_buy, _amount, _price, check=True)
                self.orders_init.append(waiting_order_id, _buy, _amount, _price)
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None
                self.tp_error = True
        else:
            self.message_log(f"Order {place_order_id} can't be placed. Check it manually", LogLevel.ERROR, tlg=True)
            if self.orders_init.exist(place_order_id):
                self.orders_init.remove(place_order_id)
            elif place_order_id == self.tp_wait_id:
                self.tp_wait_id = None

    def on_cancel_order_success(self, order_id: int, canceled_order: Order) -> None:
        if self.orders_grid.exist(order_id):
            self.message_log(f"Processing canceled grid order {order_id}", log_level=LogLevel.INFO)
            self.part_amount.pop(order_id, None)
            self.grid_order_canceled = None
            self.orders_grid.remove(order_id)
            save = True
            for o in self.get_buffered_completed_trades():
                if o.order_id == order_id:
                    save = False
                    break
            if save:
                self.orders_save.append(canceled_order.id,
                                        canceled_order.buy,
                                        f2d(canceled_order.amount),
                                        f2d(canceled_order.price))
            self.cancel_grid()
        elif order_id == self.cancel_order_id:
            self.message_log(f"Processing canceled TP order {order_id}", log_level=LogLevel.INFO)
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
            self.message_log(f"On cancel order {order_id} {error}, retry", LogLevel.ERROR)
            self.cancel_order(order_id)
        elif not STANDALONE:
            self.message_log(f"On cancel order {order_id} {error}", LogLevel.ERROR)
            if self.orders_grid.exist(order_id):
                self.message_log("It's was grid order, probably filled", LogLevel.WARNING)
                self.grid_order_canceled = None
                _buy, _amount, _price = self.orders_grid.get_by_id(order_id)
                amount_first = _amount
                amount_second = _amount * _price
                self.avg_rate = amount_second / amount_first
                self.message_log(f"Executed amount: First: {amount_first}, Second: {amount_second},"
                                 f" price: {self.avg_rate}")
                # Remove grid order with =id from order list
                self.orders_grid.remove(order_id)
                self.grid_handler(_amount_first=amount_first, _amount_second=amount_second, after_full_fill=True)
            elif order_id == self.cancel_order_id:
                self.message_log("It's was take profit", LogLevel.ERROR)
                amount_first = self.tp_order[1]
                amount_second = self.tp_order[1] * self.tp_order[2]
                self.tp_was_filled = (amount_first, amount_second, True)
                self.tp_order_id = None
                self.tp_order = ()
                self.message_log(f"Was filled TP: {self.tp_was_filled}", log_level=LogLevel.DEBUG)
                self.cancel_grid()
            else:
                self.message_log("It's unknown", LogLevel.ERROR)
        else:
            self.message_log(f"On cancel order {order_id} {error}", LogLevel.ERROR)
