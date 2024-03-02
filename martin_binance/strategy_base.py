"""
martin-binance base class and methods definitions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.0rc1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import ast
import asyncio
import csv
import logging
import queue
import random
import sqlite3
import time
import traceback
from abc import abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from shutil import rmtree, copy
from typing import Dict, List

import grpc
import jsonpickle
import orjson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import ujson as json
from colorama import init as color_init
from exchanges_wrapper import api_pb2, api_pb2_grpc
from google.protobuf import json_format
from tqdm import tqdm

import martin_binance.params as prm
from martin_binance import LAST_STATE_PATH, BACKTEST_PATH, HEARTBEAT, KLINES_INIT, EQUAL_STR, ORDER_TIMEOUT
from martin_binance.backtest.exchange_simulator import Account as backTestAccount
from martin_binance.backtest.optimizer import run_optimize, OPTIMIZER, PARAMS_FLOAT
from martin_binance.client import Trade
from martin_binance.lib import Candle, TradingCapabilityManager, Ticker, FundsEntry, OrderBook, Style, LogLevel, \
    any2str, PrivateTrade, Order, convert_from_minute, write_log, OrderUpdate, load_file, load_last_state, Klines

logger = logging.getLogger('logger')
loop = asyncio.get_event_loop()
color_init()

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [
    ('grpc.lb_policy_name', 'pick_first'),
    ('grpc.enable_retries', 0),
    ('grpc.keepalive_timeout_ms', 10000)
]

RATE_LIMITER = HEARTBEAT * 5
KLINES_LIM = 50  # Number of candles must be <= 1000
CANCEL_ALL_ORDERS = True  # Ask about cancel all active orders before start strategy and par.LOAD_LAST_STATE = 0
TRADES_LIST_LIMIT = 50
TRY_LIMIT = 30
PYARROW_BATCH_BUFFER_SIZE = 20480  # Rows
ORDER_BOOK_PRKT = "order_book.parquet"
TICKER_PRKT = "ticker.parquet"
MS_ORDER_ID = 'ms.order_id'
MS_ORDERS = 'ms.orders'
O_DEC = Decimal()
SAVE_TRADE_QUEUE = asyncio.Queue()


class StrategyBase:
    def __init__(self):
        self.session = None
        self.client: api_pb2.OpenClientConnectionId = None
        self.exchange = str()
        self.symbol = str()
        self.channel = None
        self.stub = api_pb2_grpc.MartinStub
        self.client_id = int()
        self.info_symbol = {}
        self.base_asset = str()
        self.quote_asset = str()
        self.ticker = {}
        self.funds = {}
        self.order_book = {}
        self.order_id = int(datetime.now().strftime("%S%M")) * 1000
        self.wait_order_id = []  # List of placed orders for time-out detect
        self.canceled_order_id = []  # List canceled orders for time-out detect
        self.trades = []  # List of trades associated with strategy (limit = TRADES_LIST_LIMIT)
        self.orders = {}  # {int(id): Order(), } of orders associated with strategy
        self.tcm = None  # TradingCapabilityManager
        self.last_state = None
        self.rate_limiter = RATE_LIMITER
        self.start_time_ms = int(time.time() * 1000)
        self.send_request = None
        self.for_request = None
        self.wss_fire_up = False
        self.backtest = {}
        self.delay_ordering_s = 0.5
        self.bulk_orders_cancel = {}
        self.session_root = None
        self.state_file = None
        self.operational_status = None
        #
        self.time_operational = {'ts': 0.0, 'diff': 0.0, 'new': 0.0}  # - See get_time()
        self.account = backTestAccount(prm.SAVE_DS) if prm.MODE == 'S' else None
        self.get_buffered_funds_last_time = self.get_time()
        self.queue_to_tlg = queue.Queue() if prm.TOKEN and prm.MODE != 'S' else None
        self.status_time = None  # + Last time sending status message
        self.tlg_header = ''  # - Header for Telegram message
        self.start_collect = None
        # Init in reset_backtest_vars()
        self.s_ticker = None
        self.s_order_book = None
        self.klines = None
        self.candles = None
        self.grid_buy = None
        self.grid_sell = None
        #
        self.reset_backtest_vars()
        # 
        self.cycle_time = None  # + Cycle start time
        self.command = None  # + External input command from Telegram
        self.part_amount = {}  # + {order_id: (Decimal(str(amount_f)), Decimal(str(amount_s)))} of partially filled
        self.tp_part_amount_first = O_DEC  # + Sum partially filled TP
        self.tp_part_amount_second = O_DEC  # + Sum partially filled TP
        self.connection_analytic = None  # - Connection to .db

    def __call__(self):
        return self

    def reset_backtest_vars(self):
        self.s_ticker: dict[str, pq.ParquetWriter | list] = {'pylist': []} if prm.MODE in ('TC', 'S') else None
        self.s_order_book: dict[str, pq.ParquetWriter | list] = {'pylist': []} if prm.MODE in ('TC', 'S') else None
        self.klines = {}  # KLines snapshot
        if prm.MODE in ('TC', 'S'):
            self.candles = {}
            for i in KLINES_INIT:
                self.candles.update({f"pylist_{i.value}": []})
        self.grid_buy = {}
        self.grid_sell = {}

    def reset_vars(self):
        self.ticker = {}
        self.funds = {}
        self.order_book = {}
        self.order_id = int(datetime.now().strftime("%S%M")) * 1000
        self.wait_order_id = []  # List of placed orders for time-out detect
        self.canceled_order_id = []  # List canceled orders  for time-out detect
        self.trades = []  # List of trades associated with strategy (limit = TRADES_LIST_LIMIT)
        self.orders = {}  # Set of orders associated with strategy
        self.get_buffered_funds_last_time = self.get_time()
        self.rate_limiter = RATE_LIMITER
        self.start_time_ms = int(time.time() * 1000)
        self.backtest = {}
        self.bulk_orders_cancel = {}

    def update_vars(self, _session):
        self.client = _session.client
        self.stub = _session.stub
        self.channel = _session.channel
        self.client_id = _session.client.client_id if _session.client else None
        self.exchange = _session.client.exchange if _session.client else None
        self.send_request = _session.send_request
        self.for_request = _session.for_request

    ###

    def last_state_update(self, last_state):
        last_state[MS_ORDER_ID] = json.dumps(self.order_id)
        last_state['ms_start_time_ms'] = json.dumps(self.start_time_ms)
        last_state[MS_ORDERS] = jsonpickle.encode(self.orders, keys=True)
    ###

    def get_trading_capability_manager(self) -> TradingCapabilityManager:
        return self.tcm

    def get_first_currency(self) -> str:
        return self.info_symbol.get('baseAsset')

    def get_second_currency(self) -> str:
        return self.info_symbol.get('quoteAsset')

    def get_buffered_ticker(self) -> Ticker:
        # print(f"get_buffered_ticker.ticker: {self.ticker}")
        return Ticker(self.ticker)

    def get_buffered_funds(self) -> Dict[str, FundsEntry]:
        # print(f"get_buffered_funds.funds: {self.funds}")
        if self.get_time() - self.get_buffered_funds_last_time > self.rate_limiter:
            loop.create_task(self.buffered_funds(print_info=False))
            self.get_buffered_funds_last_time = self.get_time()
        return {self.base_asset: FundsEntry(self.funds[self.base_asset]),
                self.quote_asset: FundsEntry(self.funds[self.quote_asset])}

    def get_buffered_order_book(self) -> OrderBook:
        # print(f"get_buffered_order_book.order_book: {self.order_book}")
        return OrderBook(self.order_book, _tcm=self.tcm)

    def get_buffered_completed_trades(self) -> List[PrivateTrade]:
        return self.trades

    def get_buffered_open_orders(self) -> List[Order]:
        return list(self.orders.values())

    def get_buffered_open_order(self, _id) -> Order:
        return self.orders.get(_id)

    @staticmethod
    def get_buffered_recent_candles(
            candle_size_in_minutes: int,
            number_of_candles: int = 50,
            include_current_building_candle: bool = False
    ) -> List[Candle]:
        size = convert_from_minute(candle_size_in_minutes)
        kline = Klines.get_kline(size)
        if len(kline) > number_of_candles + 1:
            return kline[-number_of_candles - (0 if include_current_building_candle else 1):
                         None if include_current_building_candle else -1]
        return kline[:None if include_current_building_candle else -1]

    def get_time(self) -> float:
        current_time = time.time()
        if self.time_operational['new']:
            diff = current_time - self.time_operational['diff'] if self.time_operational['diff'] else 0.0
            last = max(self.time_operational['new'], self.time_operational['ts'] + diff)
            self.time_operational['diff'] = current_time
            self.time_operational['ts'] = last
        else:
            last = current_time
        return last

    def transfer_to_master(self, symbol: str, amount: str):
        if prm.MODE in ('T', 'TC'):
            loop.create_task(self.transfer2master(symbol, amount))

    def place_limit_order(self, buy: bool, amount: Decimal, price: Decimal) -> int:
        self.order_id += 1
        self.message_log(f"Send order id:{self.order_id} for {'BUY' if buy else 'SELL'}"
                         f" {any2str(amount)} by {any2str(price)} = {any2str(amount * price)}",
                         color=Style.B_YELLOW)
        loop.create_task(self.place_limit_order_timeout(self.order_id))
        loop.create_task(self.create_limit_order(self.order_id, buy, any2str(amount), any2str(price)))
        if self.exchange == 'huobi':
            time.sleep(0.02)
        return self.order_id

    def cancel_order(self, order_id: int, cancel_all=False) -> None:
        loop.create_task(self.cancel_order_timeout(order_id))
        loop.create_task(self.cancel_order_call(order_id, cancel_all))

    def message_log(self, msg: str, log_level=LogLevel.INFO, tlg=False, color=Style.WHITE) -> None:
        if prm.LOGGING:
            if tlg and color == Style.WHITE:
                color = Style.B_WHITE
            if log_level in (LogLevel.ERROR, LogLevel.CRITICAL):
                tlg = True
                color = Style.B_RED
            color_msg = color + msg + Style.RESET if color else msg
            if log_level not in prm.LOG_LEVEL_NO_PRINT:
                if prm.MODE in ('T', 'TC'):
                    print(f"{datetime.now().strftime('%d/%m %H:%M:%S')} {color_msg}")
                else:
                    tqdm.write(f"{datetime.fromtimestamp(self.get_time()).strftime('%H:%M:%S.%f')[:-3]} {color_msg}")
            if prm.MODE in ('T', 'TC'):
                write_log(log_level, msg)
                if tlg and self.queue_to_tlg:
                    msg = self.tlg_header + msg
                    self.status_time = self.get_time()
                    self.queue_to_tlg.put(msg)
        elif log_level in (logging.ERROR, logging.CRITICAL):
            write_log(log_level, msg)

    #
    def order_exist(self, _id) -> bool:
        return bool(self.orders.get(int(_id)))

    def trade_not_exist(self, _order_id: int, _trade_id: int) -> bool:
        return all(
            trade.order_id != _order_id or trade.id != _trade_id
            for trade in self.trades
        )

    def order_trades_sum(self, _order_id: int) -> Decimal:
        saved_filled_quantity = Decimal()
        for _trade in self.trades:
            if _trade.order_id == _order_id:
                saved_filled_quantity += _trade.amount
        return saved_filled_quantity

    def remove_from_orders_lists(self, _order_id_list: []) -> None:
        [self.orders.pop(i, None) for i in _order_id_list]

    def remove_from_trades_lists(self, _order_id) -> None:
        self.trades[:] = [i for i in self.trades if i.order_id != _order_id]

    #
    async def backtest_control(self):
        """
        Managing backtest and optimization cycles
        """
        delay = HEARTBEAT * 30  # 1 min
        ts = time.time()
        restart = False
        while 1:
            if self.start_collect and time.time() - ts > prm.SAVE_PERIOD:
                self.start_collect = False
                self.session_data_handler()
                self.reset_backtest_vars()
                if prm.SELF_OPTIMIZATION and self.command != 'stopped':
                    _ts = datetime.utcnow()
                    storage_name = Path(self.session_root, "_study.db")
                    try:
                        _res = await run_optimize(
                            OPTIMIZER,
                            f"{self.exchange}_{self.symbol}",
                            Path(self.session_root, Path(prm.PARAMS).name),
                            str(prm.N_TRIALS),
                            f"sqlite:///{storage_name}"
                        )
                        _res = orjson.loads(_res)
                    except (asyncio.CancelledError, KeyboardInterrupt):
                        break
                    except Exception as err:
                        logger.warning(f"Backtest control: {err}")
                    else:
                        storage_name.replace(storage_name.with_name('study.db'))
                        if _res:
                            self.message_log(f"Updating strategy parameters from backtest optimal,"
                                             f" predicted value {_res.pop('_value')} ->"
                                             f" {_res.pop('new_value')}",
                                             color=Style.B_WHITE, tlg=True)
                            for key, value in _res.items():
                                self.message_log(f"{key}: {getattr(prm, key)} -> {value}")
                                setattr(
                                    prm, key,
                                    value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}")
                                )
                        self.message_log(
                            f"Strategy parameters are optimal now. Optimization cycle duration"
                            f" {str(datetime.utcnow() - _ts + timedelta(seconds=prm.SAVE_PERIOD)).rsplit('.')[0]}",
                            color=Style.B_WHITE, tlg=True
                        )
                        restart = True
                else:
                    break

            if restart and not self.part_amount and not self.tp_part_amount_first:
                restart = False
                self.parquet_declare(Path(self.session_root, "raw"))
                # Refresh klines init
                for i in KLINES_INIT:
                    try:
                        res = await self.send_request(self.stub.FetchKlines, api_pb2.FetchKlinesRequest,
                                                      symbol=self.symbol,
                                                      interval=i.value,
                                                      limit=KLINES_LIM)
                    except Exception as ex:
                        logger.warning(f"FetchKlines: {ex}")
                    else:
                        self.klines[i.value] = json_format.MessageToDict(res)
                # Save current strategy state for backtesting
                last_state = self.save_strategy_state(return_only=True)
                self.last_state_update(last_state)
                with self.state_file.open(mode='w') as outfile:
                    json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                #
                self.start_collect = True
                ts = time.time()
                self.message_log("Start data collect", tlg=True)
            await asyncio.sleep(delay)
        self.message_log("Backtest data collect and optimize session ended", tlg=True)

    def session_data_handler(self):
        """
        Save raw data for back testing and session snapshot for compare.
        """
        # Finalize ticker file
        if _ticker := self.s_ticker['pylist']:
            self.s_ticker['writer'].write_batch(
                pa.RecordBatch.from_pylist(mapping=_ticker)
            )
            self.s_ticker['pylist'].clear()
        self.s_ticker['writer'].close()

        # Finalize order_book file
        if _order_book := self.s_order_book['pylist']:
            self.s_order_book['writer'].write_batch(
                pa.RecordBatch.from_pylist(mapping=_order_book)
            )
            self.s_order_book['pylist'].clear()
        self.s_order_book['writer'].close()

        # Save klines snapshot
        if _klines := self.klines:
            with open(Path(self.session_root, "raw", "klines.json"), 'w') as f:
                json.dump(_klines, f)

        # Finalize candles files
        for i in KLINES_INIT:
            if _candles := self.candles[f"pylist_{i.value}"]:
                self.candles[f"writer_{i.value}"].write_batch(
                    pa.RecordBatch.from_pylist(mapping=_candles)
                )
                self.candles[f"pylist_{i.value}"].clear()
            self.candles[f"writer_{i.value}"].close()

        if prm.SAVE_DS:
            # Save session detail for analytics
            session_data = Path(self.session_root, "snapshot")
            session_data.mkdir(parents=True, exist_ok=True)
            #
            df_grid_sell = pd.DataFrame().from_dict(self.grid_sell, orient='index')
            df_grid_sell.index = pd.to_datetime(df_grid_sell.index, unit='ms')
            df_grid_sell.to_pickle(Path(session_data, "sell.pkl"))
            #
            df_grid_buy = pd.DataFrame().from_dict(self.grid_buy, orient='index')
            df_grid_buy.index = pd.to_datetime(df_grid_buy.index, unit='ms')
            df_grid_buy.to_pickle(Path(session_data, "buy.pkl"))

        self.message_log(f"Stream data for backtesting saved to {self.session_root}")

    def parquet_declare(self, raw_path):
        """
        pyarrow and parquet declare
        """
        schema = pa.schema([("key", pa.int64()), ("row", pa.binary())])
        self.s_ticker['writer'] = pq.ParquetWriter(Path(raw_path, TICKER_PRKT), schema=schema)
        self.s_order_book['writer'] = pq.ParquetWriter(Path(raw_path, ORDER_BOOK_PRKT), schema=schema)
        for i in KLINES_INIT:
            self.candles[f"writer_{i.value}"] = pq.ParquetWriter(Path(
                raw_path, f"candles_{i.value}.parquet"), schema=schema
            )

    ###

    def back_test_handler(self):
        # Test result handler
        s_profit = prm.SESSION_RESULT['profit'] = f"{self.get_sum_profit()}"
        s_free = prm.SESSION_RESULT['free'] = f"{self.get_free_assets(mode='free', backtest=True)[2]}"
        if prm.LOGGING:
            print(f"Session profit: {s_profit}, free: {s_free}, total: {float(s_profit) + float(s_free)}")
            test_time = datetime.utcnow() - self.cycle_time
            original_time = (self.backtest['ticker_index_last'] - self.backtest['ticker_index_first']) / 1000
            original_time = timedelta(seconds=original_time)
            print(f"Original time: {original_time}, test time: {test_time}, x = {original_time / test_time:.2f}")
        if prm.SAVE_DS:
            self._back_test_handler_ext()
        loop.stop()

    def _back_test_handler_ext(self):
        # Save test data
        session_path = Path(BACKTEST_PATH,
                            f"{self.exchange}_{self.symbol}_{datetime.now().strftime('%m%d-%H-%M-%S')}")
        session_path.mkdir(parents=True)
        ds_ticker = pd.Series(self.account.ticker).astype(float)
        ds_ticker.index = pd.to_datetime(ds_ticker.index, unit='ms')
        df_grid_sell = pd.DataFrame().from_dict(self.account.grid_sell, orient='index').astype(float)
        df_grid_sell.index = pd.to_datetime(df_grid_sell.index, unit='ms')
        df_grid_buy = pd.DataFrame().from_dict(self.account.grid_buy, orient='index').astype(float)
        df_grid_buy.index = pd.to_datetime(df_grid_buy.index, unit='ms')
        #
        ds_ticker.to_pickle(Path(session_path, "ticker.pkl"))
        df_grid_sell.to_pickle(Path(session_path, "sell.pkl"))
        df_grid_buy.to_pickle(Path(session_path, "buy.pkl"))
        copy(prm.PARAMS, Path(session_path, Path(prm.PARAMS).name))
        if prm.LOGGING:
            print(f"Session data saved to: {session_path}")

    def restore_state_before_backtesting(self):
        saved_state = load_file(self.state_file)
        self.order_id = json.loads(saved_state.pop(MS_ORDER_ID, "0"))
        self.orders = jsonpickle.decode(saved_state.pop(MS_ORDERS, '{}'), keys=True)
        self.restore_state_before_backtesting_ex(saved_state)

    #

    async def heartbeat(self, _session):
        # print(f"tik-tak:' {int(time.time() * 1000)}")
        last_exec_time = time.time()
        while 1:
            try:
                last_state = self.save_strategy_state()
                if prm.MODE in ('T', 'TC'):
                    self.last_state_update(last_state)
                    # print(f"heartbeat.last_state: {last_state}")
                    if prm.LAST_STATE_FILE.exists():
                        prm.LAST_STATE_FILE.replace(prm.LAST_STATE_FILE.with_suffix('.prev'))
                    with prm.LAST_STATE_FILE.open(mode='w') as outfile:
                        json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                    #
                    update_max_queue_size = False
                    if self.operational_status and (time.time() - last_exec_time > HEARTBEAT * 30):
                        last_exec_time = time.time()
                        try:
                            res = await self.send_request(
                                self.stub.CheckStream,
                                api_pb2.MarketRequest,
                                symbol=self.symbol
                            )
                        except Exception as ex:
                            logger.warning(f"Exception on Check WSS: {ex}")
                        else:
                            if not res.success:
                                logger.warning(f"Not active WSS for {self.symbol} on {self.exchange},"
                                               f" restart request sent")
                                update_max_queue_size = True
                                self.wss_fire_up = True
                    #
                    if self.client_id and self.wss_fire_up:
                        try:
                            if await self.session.get_client():
                                self.update_vars(self.session)
                                await self.send_request(
                                    self.stub.StopStream,
                                    api_pb2.MarketRequest,
                                    symbol=self.symbol
                                )
                                await self.wss_init(update_max_queue_size=update_max_queue_size)
                                self.wss_fire_up = False
                        except Exception as ex:
                            logger.warning(f"Exception on fire up WSS: {ex}")
                            self.wss_fire_up = True
                await asyncio.sleep(HEARTBEAT)
            except (KeyboardInterrupt, asyncio.CancelledError):
                break

    async def save_asset(self):
        """
        Update account asset list and value in t_asset
        """
        connection_analytic = None
        while connection_analytic is None:
            connection_analytic = self.connection_analytic
            await asyncio.sleep(HEARTBEAT)
        delay = HEARTBEAT * 300  # 10 min
        max_use_update = 60 * 60 * 24  # 24h if the row has not been updated that the asset is not traded
        while True:
            try:
                res = await self.send_request(self.stub.FetchAccountInformation, api_pb2.OpenClientConnectionId)
            except asyncio.CancelledError:
                pass
            except Exception as _ex:
                logger.warning(f"Exception save_asset: {_ex}")
            else:
                balances = json_format.MessageToDict(res).get('balances', [])
                # Refresh actual balance
                try:
                    balance_f = next(item for item in balances if item["asset"] == self.base_asset)
                except StopIteration:
                    balance_f = {'asset': self.base_asset, 'free': '0.0', 'locked': '0.0'}
                try:
                    balance_s = next(item for item in balances if item["asset"] == self.quote_asset)
                except StopIteration:
                    balance_s = {'asset': self.base_asset, 'free': '0.0', 'locked': '0.0'}
                funds = {self.base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                         self.quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
                self.funds = funds
                # Get asset balances from Funding Wallet
                cursor = connection_analytic.cursor()
                try:
                    cursor.execute('SELECT 1 FROM t_asset WHERE id_exchange=:id_exchange AND use=:use',
                                   {'id_exchange': prm.ID_EXCHANGE, 'use': 1})
                    main_active = cursor.fetchone()
                    cursor.close()
                except sqlite3.Error as err:
                    cursor.close()
                    main_active = (2,)
                    print(f"SELECT from t_asset: {err}")
                funding_wallet = []
                assets_fw = {}
                if self.exchange not in ('bitfinex', 'huobi'):
                    try:
                        res = await self.send_request(self.stub.FetchFundingWallet, api_pb2.FetchFundingWalletRequest)
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
                    if self.exchange != 'bitfinex':
                        total = assets_fw.pop(balance['asset'], Decimal('0.0'))
                    else:
                        total = Decimal('0.0')
                    if balance['asset'] not in (self.base_asset, self.quote_asset) or prm.GRID_ONLY:
                        total += Decimal(balance['free']) + Decimal(balance['locked'])
                    assets[balance['asset']] = float(total)
                cursor_analytic = connection_analytic.cursor()
                try:
                    cursor_analytic.execute('SELECT id_exchange, currency, value, use, timestamp\
                                             FROM t_asset\
                                             WHERE id_exchange=:id_exchange',
                                            {'id_exchange': prm.ID_EXCHANGE})
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
                                   {'id_exchange': prm.ID_EXCHANGE, 'use': 0})
                    for row in rows:
                        if row[1] in (self.base_asset, self.quote_asset) and main_active == (1,):
                            amount = float(assets.pop(row[1], 0))
                            cursor.execute('UPDATE t_asset SET value=:value, timestamp=:timestamp, use=:use\
                                            WHERE id_exchange=:id_exchange\
                                            and currency=:currency',
                                           {
                                               'value': amount if prm.GRID_ONLY else 0,
                                               'timestamp': int(time.time()),
                                               'use': 1,
                                               'id_exchange': prm.ID_EXCHANGE,
                                               'currency': row[1]}
                                           )
                        elif row[3]:
                            # Check used currency from other pair for last update time
                            if time.time() - row[4] > max_use_update:
                                cursor.execute('DELETE FROM t_asset\
                                                WHERE id_exchange=:id_exchange\
                                                and currency=:currency',
                                               {'id_exchange': prm.ID_EXCHANGE, 'currency': row[1]})
                            assets.pop(row[1], None)
                    if assets:
                        for key, value in assets.items():
                            use = 1 if key in (self.base_asset, self.quote_asset) else 0
                            cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                           (prm.ID_EXCHANGE, key, value, use, int(time.time())))
                    if assets_fw:
                        for key, value in assets_fw.items():
                            cursor.execute('INSERT into t_asset values(?, ?, ?, ?, ?)',
                                           (prm.ID_EXCHANGE, key, float(value), 0, int(time.time())))
                    cursor.execute('COMMIT')
                    cursor.close()
                except sqlite3.Error as err:
                    cursor.execute('ROLLBACK')
                    cursor.close()
                    logger.warning(f"Refresh t_asset: {err}")
            await asyncio.sleep(delay)

    async def ask_exit(self):
        self.message_log("Got signal for exit", color=Style.MAGENTA)
        self.operational_status = False
        if prm.MODE in ('T', 'TC'):
            await asyncio.sleep(HEARTBEAT)
            try:
                await self.send_request(self.stub.StopStream, api_pb2.MarketRequest, symbol=self.symbol)
            except Exception as ex:
                logger.warning(f"ask_exit: {ex}")

            if prm.MODE == 'TC' and self.start_collect:
                # Save stream data for backtesting
                self.start_collect = False
                self.session_data_handler()

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)
        if prm.LOGGING:
            print(f"Cancelling {len(tasks)} outstanding tasks")
        try:
            self.stop()
        except Exception as _err:
            print(f"ask_exit.strategy.stop: {_err}")
        await self.channel.close()
        if prm.MODE in ('T', 'TC') and prm.LAST_STATE_FILE.exists():
            print(f"Current state saved into {prm.LAST_STATE_FILE}")

    async def fetch_order(self, _id: int, _client_order_id: str = None, _filled_update_call=False):
        try:
            res = await self.send_request(
                self.stub.FetchOrder, api_pb2.FetchOrderRequest,
                symbol=self.symbol,
                order_id=_id,
                client_order_id=_client_order_id,
                filled_update_call=_filled_update_call
            )
            result = json_format.MessageToDict(res)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except Exception as _ex:
            self.message_log(f"Exception in fetch_order: {_ex}", log_level=LogLevel.ERROR)
            return {}
        else:
            self.message_log(f"For order {_id}({_client_order_id}) fetched status is {result.get('status')}",
                             log_level=LogLevel.INFO, color=Style.GREEN)
            if result:
                return result
            self.message_log(f"Can't get status for order {_id}({_client_order_id})",
                             log_level=LogLevel.WARNING)
            return {}

    async def on_funds_update(self):
        if prm.MODE in ('T', 'TC'):
            try:
                async for _funds in self.for_request(
                        self.stub.OnFundsUpdate, api_pb2.OnFundsUpdateRequest,
                        symbol=self.symbol,
                        base_asset=self.base_asset,
                        quote_asset=self.quote_asset
                ):
                    funds = json.loads(json.loads(json_format.MessageToJson(_funds))['funds'])
                    if funds.get(self.base_asset) or funds.get(self.quote_asset):
                        self.on_funds_update_handler(funds)
            except Exception as ex:
                logger.warning(f"Exception on WSS, on_funds_update loop closed: {ex}")
                logger.debug(f"Exception traceback: {traceback.format_exc()}")
                self.wss_fire_up = True
        else:
            funds = {}
            _funds = self.account.funds.get_funds()
            [funds.update({d.get('asset'): {'free': d.get('free'), 'locked': d.get('locked')}}) for d in _funds]
            self.on_funds_update_handler(funds)

    def on_funds_update_handler(self, funds):
        self.funds.update(funds)
        funds = {self.base_asset: FundsEntry(self.funds[self.base_asset]),
                 self.quote_asset: FundsEntry(self.funds[self.quote_asset])}
        self.on_new_funds(funds)
        self.get_buffered_funds_last_time = self.get_time()

    async def loop_ds(self, ds, ticker=False):
        while not self.start_collect:
            await asyncio.sleep(0.001)

        batches = ds.iter_batches(PYARROW_BATCH_BUFFER_SIZE)
        index_prev = 0
        for batch in batches:
            for row in batch.to_pylist():
                index = row.pop('key') / 1000
                if ticker:
                    self.time_operational['new'] = index
                    delay = index - index_prev if index_prev else 0
                    index_prev = index
                else:
                    delay = index - self.get_time()

                if delay > 0:
                    delay /= prm.XTIME
                    await asyncio.sleep(delay)
                yield orjson.loads(row['row'])
        if ticker:
            self.backtest['ticker_index_last'] = index_prev * 1000

    async def aiter_candles(self, _klines: {str: Klines}, _i: str):
        async for row in self.loop_ds(self.backtest[f"candles_{_i}"]):
            _klines.get(_i).refresh(row)
        self.message_log(f"Backtest candles *** {_i} *** timeSeries ended")

    def open_orders_snapshot(self, ts=None):
        orders_buy = {}
        orders_sell = {}
        for k, order in self.orders.items():
            if order.buy:
                orders_buy[k] = order.price
            else:
                orders_sell[k] = order.price
        self.grid_buy.update({ts or int(time.time() * 1000): pd.Series(orders_buy)})
        self.grid_sell.update({ts or int(time.time() * 1000): pd.Series(orders_sell)})

    async def cancel_order_call(self, _id: int, cancel_all=False, count=0):
        if count == 0:
            self.canceled_order_id.append(_id)
        elif _id in self.canceled_order_id:
            self.canceled_order_id.remove(_id)
        _fetch_order = False
        try:
            if prm.MODE in ('T', 'TC'):
                if cancel_all:
                    if _id not in self.bulk_orders_cancel:
                        res = await asyncio.wait_for(
                            self.send_request(
                                self.stub.CancelAllOrders,
                                api_pb2.MarketRequest,
                                symbol=self.symbol
                            ),
                            timeout=ORDER_TIMEOUT - 5
                        )
                        if res:
                            for v in ast.literal_eval(json.loads(res.result)):
                                self.bulk_orders_cancel.update({v['orderId']: v})
                    result = self.bulk_orders_cancel.pop(_id, None)
                else:
                    res = await self.send_request(self.stub.CancelOrder, api_pb2.CancelOrderRequest,
                                                  symbol=self.symbol,
                                                  order_id=_id)
                    result = json_format.MessageToDict(res)
            else:
                result = self.account.cancel_order(order_id=_id, ts=int(self.get_time() * 1000))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except asyncio.TimeoutError:
            # TODO timeout event not raised exception
            _fetch_order = True
            self.message_log(f"Timeout on cancel order {_id}")
        except grpc.RpcError as ex:
            _fetch_order = True
            self.message_log(f"Exception on cancel order {_id}: {ex.code().name}, {ex.details()}")
        except Exception as _ex:
            _fetch_order = True
            self.message_log(f"Exception on cancel order call for {_id}: {_ex}")
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
        else:
            # print(f"cancel_order_call.result: {result}")
            # Remove from orders lists
            if result and result.get('status') == 'CANCELED':
                await self.cancel_order_handler(_id, cancel_all)
            else:
                self.message_log(f"Cancel order {_id}: Warning, not result getting")
                _fetch_order = True
        finally:
            if _fetch_order:
                res = await self.fetch_order(_id, _filled_update_call=True)
                if res.get('status') == 'CANCELED':
                    await self.cancel_order_handler(_id, cancel_all)
                elif res.get('status') == 'FILLED':
                    if _id in self.canceled_order_id:
                        self.canceled_order_id.remove(_id)
                elif not res or res.get('status') in ('NEW', 'PARTIALLY_FILLED'):
                    await asyncio.sleep(HEARTBEAT * count)
                    if count <= TRY_LIMIT:
                        await self.cancel_order_call(_id, cancel_all=False, count=count + 1)
                    else:
                        self.on_cancel_order_error_string(_id, 'Cancel order try limit exceeded')

    async def cancel_order_handler(self, _id, cancel_all):
        if _id in self.canceled_order_id:
            self.canceled_order_id.remove(_id)
            self.message_log(f"Cancel order {_id} success", color=Style.GREEN)
        self.remove_from_orders_lists([_id])
        self.on_cancel_order_success(_id, cancel_all=cancel_all)
        if prm.MODE == 'TC' and prm.SAVE_DS and self.start_collect:
            self.open_orders_snapshot()
        elif prm.MODE == 'S':
            await self.on_funds_update()

    async def cancel_order_timeout(self, _id):
        await asyncio.sleep(ORDER_TIMEOUT)
        if _id in self.canceled_order_id:
            self.canceled_order_id.remove(_id)
            self.on_cancel_order_error_string(_id, 'Cancel order timeout')

    async def transfer2master(self, symbol: str, amount: str):
        try:
            res = await self.send_request(
                self.stub.TransferToMaster,
                api_pb2.MarketRequest,
                symbol=symbol,
                amount=amount
            )
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except grpc.RpcError as ex:
            status_code = ex.code()
            self.message_log(f"Exception transfer {symbol} to main account: {status_code.name}, {ex.details()}")
        except Exception as _ex:
            self.message_log(f"Exception transfer {symbol} to main account: {_ex}")
        else:
            if res.success:
                self.message_log(f"Sent {amount} {symbol} to main account", log_level=LogLevel.INFO)
            else:
                self.message_log(f"Not sent {amount} {symbol} to main account\n,{res.result}",
                                 log_level=LogLevel.WARNING)

    async def buffered_funds(self, print_info: bool = True):
        try:
            if prm.MODE in ('T', 'TC'):
                res = await self.send_request(self.stub.FetchAccountInformation, api_pb2.OpenClientConnectionId)
                balances = json_format.MessageToDict(res).get('balances', [])
            else:
                balances = self.account.funds.get_funds()
        except asyncio.CancelledError:
            pass
        except Exception as _ex:
            logger.warning(f"Exception buffered_funds: {_ex}")
        else:
            balance_f = next(
                (item for item in balances if item["asset"] == self.base_asset),
                {'asset': self.base_asset, 'free': '0.0', 'locked': '0.0'}
            )
            balance_s = next(
                (item for item in balances if item["asset"] == self.quote_asset),
                {'asset': self.quote_asset, 'free': '0.0', 'locked': '0.0'}
            )
            funds = {self.base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                     self.quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}}
            self.funds = funds
            if print_info and prm.LOGGING:
                print(EQUAL_STR)
                print(f"Base asset balance: {balance_f}")
                print(f"Quote asset balance: {balance_s}")
                print(EQUAL_STR)
            else:
                funds = {self.base_asset: FundsEntry(self.funds[self.base_asset]),
                         self.quote_asset: FundsEntry(self.funds[self.quote_asset])}
                self.on_new_funds(funds)

    async def place_limit_order_timeout(self, _id):
        await asyncio.sleep(ORDER_TIMEOUT)
        if _id in self.wait_order_id:
            self.wait_order_id.remove(_id)
            self.on_place_order_error(_id, 'Place order timeout')

    async def get_exchange_info(self, _request, _symbol):
        """
        Refresh trading rules for pair every 10 mins
        """
        while 1:
            try:
                _exchange_info_symbol = await _request(self.stub.FetchExchangeInfoSymbol,
                                                       api_pb2.MarketRequest,
                                                       symbol=_symbol)
            except asyncio.CancelledError:
                pass  # Task cancellation should not be logged as an error
            except Exception as _ex:
                self.message_log(f"Exception get_exchange_info: {_ex}")
            else:
                self.info_symbol = json_format.MessageToDict(_exchange_info_symbol)
                self.tcm = TradingCapabilityManager(self.info_symbol, prm.PRICE_LIMIT_RULES)
            await asyncio.sleep(600)

    async def buffered_candle(self):
        Klines.klines_lim = KLINES_LIM
        klines = {}
        klines_from_file = {}
        if prm.MODE == 'S':
            klines_from_file = json.load(open(Path(self.session_root, "raw/klines.json")))
        for i in KLINES_INIT:
            if prm.MODE in ('T', 'TC'):
                try:
                    res = await self.send_request(
                        self.stub.FetchKlines, api_pb2.FetchKlinesRequest,
                        symbol=self.symbol,
                        interval=i.value,
                        limit=KLINES_LIM
                    )
                except Exception as ex:
                    kline = {}
                    logger.warning(f"FetchKlines: {ex}")
                else:
                    kline = json_format.MessageToDict(res)
                    if prm.MODE == 'TC' and (self.start_collect or self.start_collect is None):
                        self.klines[i.value] = kline
            else:
                kline = klines_from_file.get(i.value, {})

            if candles := kline.get('klines'):
                kline_i = Klines(i.value)
                for candle in candles:
                    kline_i.refresh(json.loads(candle))
                    # print(f"buffered_candle.candle: {candle}")
                klines[i.value] = kline_i

        if len(klines) == len(KLINES_INIT):
            loop.create_task(self.on_klines_update(klines))
        else:
            logger.info("Init buffered candle failed. try one else...")
            await asyncio.sleep(random.uniform(1, 5))
            self.wss_fire_up = True

    async def on_klines_update(self, _klines: {str: Klines}):
        _intervals = list(_klines.keys())
        if prm.MODE in ('T', 'TC'):
            try:
                async for res in self.for_request(self.stub.OnKlinesUpdate, api_pb2.FetchKlinesRequest,
                                                  symbol=self.symbol,
                                                  interval=json.dumps(_intervals)):
                    candle = json.loads(res.candle)
                    _klines.get(res.interval).refresh(candle)
                    if prm.MODE == 'TC' and (self.start_collect or self.start_collect is None):
                        if len(self.candles[f"pylist_{res.interval}"]) > PYARROW_BATCH_BUFFER_SIZE:
                            self.candles[f"writer_{res.interval}"].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.candles[f"pylist_{res.interval}"])
                            )
                            self.candles[f"pylist_{res.interval}"].clear()

                        self.candles[f"pylist_{res.interval}"].append(
                            {"key": int(time.time() * 1000), "row": orjson.dumps(candle)}
                        )
            except Exception as ex:
                logger.warning(f"Exception on WSS, on_klines_update loop closed: {ex}")
                logger.debug(f"Exception traceback: {traceback.format_exc()}")
                self.wss_fire_up = True
        else:
            for i in _intervals:
                loop.create_task(self.aiter_candles(_klines, i))

    async def create_limit_order(self, _id: int, buy: bool, amount: str, price: str) -> None:
        self.wait_order_id.append(_id)
        _fetch_order = False
        try:
            if prm.MODE in ('T', 'TC'):
                ts = time.time()
                res = await self.send_request(
                    self.stub.CreateLimitOrder, api_pb2.CreateLimitOrderRequest,
                    symbol=self.symbol,
                    buy_side=buy,
                    quantity=amount,
                    price=price,
                    new_client_order_id=_id
                )
                result = json_format.MessageToDict(res)
                self.delay_ordering_s = time.time() - ts
            else:
                await asyncio.sleep(self.delay_ordering_s / prm.XTIME)
                result = self.account.create_order(
                    symbol=self.symbol,
                    client_order_id=str(_id),
                    buy=buy,
                    amount=amount,
                    price=price,
                    lt=int(self.get_time() * 1000)
                )
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except grpc.RpcError as ex:
            status_code = ex.code()
            if status_code == grpc.StatusCode.FAILED_PRECONDITION:
                if _id in self.wait_order_id:
                    # Supress call strategy handler
                    self.wait_order_id.remove(_id)
            else:
                _fetch_order = True
            self.on_place_order_error(_id, f"{status_code.name}, {ex.details()}")
        except Exception as _ex:
            _fetch_order = True
            self.message_log(f"Exception creating order {_id}: {_ex}")
        else:
            if result:
                await self.create_order_handler(_id, result)
            else:
                _fetch_order = True
        finally:
            if _fetch_order:
                await asyncio.sleep(HEARTBEAT)
                res = await self.fetch_order(0, str(_id), _filled_update_call=True)
                if res.get('status') in ('NEW', 'PARTIALLY_FILLED', 'FILLED'):
                    await self.create_order_handler(_id, res)

    async def create_order_handler(self, _id, result):
        # print(f"create_order_handler.result: {result}")
        if _id in self.wait_order_id and not self.order_exist(result['orderId']):
            self.wait_order_id.remove(_id)
            order = Order(result)
            self.message_log(
                f"Order placed {order.id}({result.get('clientOrderId') or _id}) for {result.get('side')}"
                f" {any2str(order.amount)} by {any2str(order.price)} = {any2str(order.amount * order.price)}",
                color=Style.GREEN)
            self.orders[order.id] = order

            if prm.MODE == 'S':
                await self.on_funds_update()
            elif prm.MODE == 'TC' and self.start_collect:
                executed_qty = Decimal(result['executedQty'])
                cummulative_quote_qty = Decimal(result['cummulativeQuoteQty'])
                if executed_qty > 0 and self.s_ticker['pylist']:
                    s_tic = self.s_ticker['pylist'].pop()
                    s_tic_row = orjson.loads(s_tic['row'])
                    s_tic_row['lastPrice'] = str(cummulative_quote_qty / executed_qty)
                    s_tic['row'] = orjson.dumps(s_tic_row)
                    self.s_ticker['pylist'].append(s_tic)
                if prm.SAVE_DS:
                    self.open_orders_snapshot()

            self.on_place_order_success(_id, order)

    async def on_balance_update(self):
        try:
            async for res in self.for_request(self.stub.OnBalanceUpdate, api_pb2.MarketRequest, symbol=self.symbol):
                _res = json.loads(res.balance)
                await SAVE_TRADE_QUEUE.put(
                    ['TRANSFER',
                     _res["event_time"],
                     _res["asset"],
                     _res["balance_delta"]]
                )
                self.on_balance_update_ex(_res)
        except Exception as ex:
            logger.warning(f"Exception on WSS, on_balance_update loop closed: {ex}")
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
            self.wss_fire_up = True

    async def on_order_update(self):
        try:
            async for event in self.for_request(self.stub.OnOrderUpdate, api_pb2.MarketRequest, symbol=self.symbol):
                # Only for registered orders on own pair
                ed = ast.literal_eval(json.loads(event.result))
                await self.on_order_update_handler(ed)
        except Exception as ex:
            logger.warning(f"Exception on WSS, on_order_update loop closed: {ex}")
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
            self.wss_fire_up = True

    async def on_order_update_handler(self, ed):
        if self.symbol != ed['symbol']:
            return
        if not self.order_exist(ed['order_id']) and ed["client_order_id"].isnumeric():
            _ed = {
                "symbol": ed['symbol'],
                "orderId": ed['order_id'],
                "orderListId": -1,
                "clientOrderId": ed["client_order_id"],
                "transactTime": ed["transaction_time"],
                "price": ed['order_price'],
                "origQty": ed['order_quantity'],
                "executedQty": ed["cumulative_filled_quantity"],
                "cummulativeQuoteQty": ed["quote_asset_transacted"],
                "status": ed['order_status'],
                "timeInForce": ed['time_in_force'],
                "type": ed['order_type'],
                "side": ed['side'],
                "workingTime": ed['order_creation_time'],
                "selfTradePreventionMode": "NONE"
            }
            await self.create_order_handler(int(ed["client_order_id"]), _ed)

        if not Decimal(ed["cumulative_filled_quantity"]):
            return

        if self.trade_not_exist(ed["order_id"], ed["trade_id"]):
            self._on_order_update_handler_ext(ed)
            await SAVE_TRADE_QUEUE.put(
                ["TRADE" if ed['is_maker_side'] else "TRADE_BY_MARKET",
                 ed["transaction_time"],
                 ed["side"],
                 ed["order_id"],
                 ed["client_order_id"],
                 ed["trade_id"],
                 ed["order_quantity"],
                 ed["order_price"],
                 ed["cumulative_filled_quantity"],
                 ed["quote_asset_transacted"],
                 ed["last_executed_quantity"],
                 ed["last_executed_price"]]
            )

        if ed['order_status'] == 'FILLED':
            # Remove from orders dict
            self.remove_from_orders_lists([ed['order_id']])
            if prm.MODE == 'TC' and self.start_collect and self.s_ticker['pylist']:
                s_tic = self.s_ticker['pylist'].pop()
                s_tic_row = orjson.loads(s_tic['row'])
                s_tic_row['lastPrice'] = ed['last_executed_price']
                s_tic['row'] = orjson.dumps(s_tic_row)
                if prm.SAVE_DS:
                    self.open_orders_snapshot()
        elif ed['order_status'] == 'PARTIALLY_FILLED':
            # Update order in orders dict
            _order = {
                "orderId": ed['order_id'],
                "price": ed['order_price'],
                "origQty": ed['order_quantity'],
                "executedQty": ed['cumulative_filled_quantity'],
                "type": ed['order_type'],
                "side": ed['side'],
                "transactTime": ed['transaction_time'],
            }
            self.orders |= {ed['order_id']: Order(_order)}

    def _on_order_update_handler_ext(self, ed):
        trade = {
            "qty": ed['last_executed_quantity'],
            "isBuyer": ed['side'] == 'BUY',
            "isMaker": ed['is_maker_side'],
            "id": ed['trade_id'],
            "orderId": ed['order_id'],
            "price": ed['last_executed_price'],
            "commission": ed['commission_amount'],
            "commissionAsset": ed['commission_asset'],
            "time": ed['transaction_time'],
        }
        self.trades.append(PrivateTrade(trade))
        # noinspection PyStatementEffect
        self.trades[-TRADES_LIST_LIMIT:]
        if ed['order_status'] == 'FILLED' and self.order_trades_sum(ed['order_id']) < Decimal(ed['order_quantity']):
            self.message_log(f"Order: {ed['order_id']} was missed partially filling event", log_level=LogLevel.INFO)
            ed['order_status'] = 'PARTIALLY_FILLED'
        self.on_order_update_ex(OrderUpdate(ed, self.trades))

    async def on_ticker_update(self):
        """
        row = {'openPrice': '26923.97000000', 'lastPrice': '26882.51000000', 'closeTime': 1684572464013}
        :return:
        """
        if prm.MODE in ('T', 'TC'):
            try:
                async for ticker in self.for_request(
                        self.stub.OnTickerUpdate,
                        api_pb2.MarketRequest,
                        symbol=self.symbol
                ):
                    ticker_24h = {'openPrice': ticker.open_price,
                                  'lastPrice': ticker.close_price,
                                  'closeTime': ticker.event_time}
                    self.ticker = ticker_24h
                    # print(f"on_ticker_update.ticker_24h: {ticker_24h}")
                    self.on_new_ticker(Ticker(self.ticker))
                    #
                    if prm.MODE == 'TC' and self.start_collect:
                        ts = int(time.time() * 1000)
                        if len(self.s_ticker['pylist']) > PYARROW_BATCH_BUFFER_SIZE:
                            self.s_ticker['writer'].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.s_ticker['pylist'])
                            )
                            self.s_ticker['pylist'].clear()
                        ticker_24h['delay'] = self.delay_ordering_s
                        # print(f"on_ticker_update.ticker_24h: {ticker_24h}")
                        self.s_ticker['pylist'].append({"key": ts, "row": orjson.dumps(ticker_24h)})
                        if prm.SAVE_DS:
                            self.open_orders_snapshot(ts=ts)
            except Exception as ex:
                logger.warning(f"Exception on WSS, on_ticker_update loop closed: {ex}")
                logger.debug(f"Exception traceback: {traceback.format_exc()}")
                self.wss_fire_up = True
        else:
            if prm.LOGGING:
                pbar = tqdm(total=self.backtest['ticker'].metadata.num_rows)
            async for row in self.loop_ds(self.backtest['ticker'], ticker=True):
                self.delay_ordering_s = row.pop('delay', 0)
                self.ticker = row
                self.on_new_ticker(Ticker(row))
                res = self.account.on_ticker_update(row, int(self.get_time() * 1000))
                for _res in res:
                    await self.on_order_update_handler(_res)
                    await self.on_funds_update()
                if prm.LOGGING:
                    # noinspection PyUnboundLocalVariable
                    pbar.update()
            if prm.LOGGING:
                pbar.close()
            self.message_log("Backtest *** ticker *** timeSeries ended")
            self.back_test_handler()

    async def on_order_book_update(self):
        if prm.MODE in ('T', 'TC'):
            try:
                async for _order_book in self.for_request(
                        self.stub.OnOrderBookUpdate,
                        api_pb2.MarketRequest,
                        symbol=self.symbol
                ):
                    order_book = order_book_prepare(_order_book)
                    self.order_book = order_book
                    self.on_new_order_book(OrderBook(self.order_book))
                    if prm.MODE == 'TC' and self.start_collect:
                        order_book['bids'] = order_book['bids'][:1]
                        order_book['asks'] = order_book['asks'][:1]
                        if len(self.s_order_book['pylist']) > PYARROW_BATCH_BUFFER_SIZE:
                            self.s_order_book['writer'].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.s_order_book['pylist'])
                            )
                            self.s_order_book['pylist'].clear()
                        self.s_order_book['pylist'].append(
                            {"key": int(time.time() * 1000), "row": orjson.dumps(order_book)}
                        )
            except Exception as ex:
                logger.warning(f"Exception on WSS, on_order_book_update loop closed: {ex}")
                logger.debug(f"Exception traceback: {traceback.format_exc()}")
                self.wss_fire_up = True
        else:
            async for row in self.loop_ds(self.backtest['order_book']):
                self.order_book = row
                self.on_new_order_book(OrderBook(row))
            self.message_log("Backtest *** order_book *** timeSeries ended")

    async def buffered_orders(self):
        exch_orders = []
        diff_id = set()
        restore = False
        while not self.operational_status:
            try:
                res = await self.send_request(self.stub.CheckStream, api_pb2.MarketRequest, symbol=self.symbol)
            except Exception as ex_1:
                logger.warning(f"Exception on Check WSS: {ex_1}")
            else:
                if res.success:
                    self.operational_status = True
            await asyncio.sleep(HEARTBEAT)
        while self.operational_status:
            try:
                res = await self.send_request(self.stub.CheckStream, api_pb2.MarketRequest, symbol=self.symbol)
                if res is None or not res.success:
                    self.wss_fire_up = True
                    raise UserWarning(f"Not active WSS for {self.symbol} on {self.exchange}, restart request sent")

                _orders = await self.send_request(self.stub.FetchOpenOrders, api_pb2.MarketRequest, symbol=self.symbol)
                if _orders is None:
                    raise UserWarning("Can't fetch open orders")

                self.rate_limiter = max(self.rate_limiter, _orders.rate_limiter)

                orders = json_format.MessageToDict(_orders).get('items', [])
                [exch_orders.append(int(_o['orderId'])) for _o in orders]

                if restore:
                    self.message_log("Trying restore saved state after lost connection to host", color=Style.GREEN)

                if self.last_state:
                    self.message_log("Trying restore saved state after restart", color=Style.GREEN)
                    self.restore_strategy_state(restore=True)

                for order in orders:
                    _id = int(order['orderId'])
                    if (order.get('status') == 'PARTIALLY_FILLED' and
                            self.order_trades_sum(_id) < Decimal(order['executedQty'])):
                        diff_id.add(_id)

                # Missed fill event list
                diff_id.update(set(self.orders).difference(set(exch_orders)))

                if diff_id:
                    self.message_log(f"Perhaps was missed event for order(s): {diff_id},"
                                     f" checking it", log_level=LogLevel.WARNING, tlg=False)
                    for _id in diff_id:
                        res = await self.fetch_order(_id, _filled_update_call=True)
                        if res.get('status') in ('CANCELED', 'EXPIRED_IN_MATCH'):
                            await self.cancel_order_handler(_id, cancel_all=False)

                if self.last_state and prm.MODE == 'TC':
                    last_state = self.save_strategy_state(return_only=True)
                    self.last_state_update(last_state)
                    with self.state_file.open(mode='w') as outfile:
                        json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                    self.start_collect = True
                exch_orders.clear()
                diff_id.clear()
                self.last_state = None
                restore = False

            except asyncio.CancelledError:
                # print("buffered_orders.Cancelled")
                self.operational_status = False
            except UserWarning as ex_2:
                self.message_log(f"Exception buffered_orders: {ex_2}", log_level=LogLevel.WARNING)
                restore = True
            except grpc.RpcError as ex_3:
                status_code = ex_3.code()
                self.message_log(f"Exception buffered_orders: {status_code.name}, {ex_3.details()}",
                                 log_level=LogLevel.WARNING, color=Style.B_RED, tlg=True)
                if status_code == grpc.StatusCode.RESOURCE_EXHAUSTED:
                    # Decrease requests frequency
                    self.rate_limiter += HEARTBEAT
                    self.message_log(f"RATE_LIMITER set to {self.rate_limiter}s", log_level=LogLevel.WARNING)
                    await asyncio.sleep(ORDER_TIMEOUT)
                    try:
                        await self.send_request(self.stub.ResetRateLimit, api_pb2.OpenClientConnectionId,
                                                rate_limiter=self.rate_limiter)
                    except Exception as ex_4:
                        logger.warning(f"Exception buffered_orders:ResetRateLimit: {ex_4}")
                else:
                    restore = True
            except Exception as ex_5:
                self.message_log(f"Exception buffered_orders: {ex_5}\n{traceback.format_exc()}",
                                 log_level=LogLevel.ERROR)
                restore = True
            await asyncio.sleep(self.rate_limiter)

    async def wss_declare(self):
        # Market stream
        loop.create_task(self.on_ticker_update())
        await self.buffered_candle()
        loop.create_task(self.on_order_book_update())
        if prm.MODE in ('T', 'TC'):
            # User Stream
            loop.create_task(self.on_funds_update())
            loop.create_task(self.on_order_update())
            loop.create_task(self.on_balance_update())
            if prm.MODE == 'TC':
                loop.create_task(self.backtest_control())

    async def wss_init(self, update_max_queue_size=False):
        self.message_log(f"Init WSS, client_id: {self.client_id}")
        if self.client_id:
            await self.wss_declare()
            # WSS start
            '''
            market_stream_count=5
            These values directly depend on the number of market ws streams used in the strategy and declared above
            '''
            self.wss_fire_up = False
            try:
                await self.send_request(self.stub.StartStream,
                                        api_pb2.StartStreamRequest,
                                        symbol=self.symbol,
                                        market_stream_count=5,
                                        update_max_queue_size=update_max_queue_size)
            except UserWarning:
                self.message_log("Start WSS failed, retry", log_level=LogLevel.WARNING)
                self.wss_fire_up = True
        else:
            self.message_log("Init WSS failed, retry", log_level=LogLevel.WARNING)
            await asyncio.sleep(random.randint(HEARTBEAT, HEARTBEAT * 5))
            self.wss_fire_up = True

    async def main(self, _symbol):
        restore_state = None
        last_state = {}
        active_orders = []
        exch_orders_ids = []
        try:
            if self.session is None:
                self.symbol = _symbol
                if len(prm.EXCHANGE) > prm.ID_EXCHANGE:
                    account_name = prm.EXCHANGE[prm.ID_EXCHANGE]
                else:
                    print(f"ID_EXCHANGE = {prm.ID_EXCHANGE} not in list. See readme 'Add new exchange'")
                    raise SystemExit(1)
                self.session = Trade(
                    channel_options=CHANNEL_OPTIONS,
                    account_name=account_name,
                    rate_limiter=self.rate_limiter,
                    symbol=_symbol
                )
                #
                await self.session.get_client()
                self.update_vars(self.session)
                send_request = self.session.send_request
                if prm.LOGGING:
                    print(f"main.account_name: {account_name}")  # lgtm [py/clear-text-logging-sensitive-data]
                    print(f"main.exchange: {self.exchange}")
                    print(f"main.client_id: {self.client_id}")
                    print(f"main.srv_version: {self.session.client.srv_version}")
                #
                if prm.MODE in ('T', 'TC'):
                    # Check and Cancel ALL ACTIVE ORDER
                    try:
                        _active_orders = await send_request(
                            self.stub.FetchOpenOrders,
                            api_pb2.MarketRequest,
                            symbol=_symbol
                        )
                    except Exception as ex:
                        print(f"Can't get active orders: {ex}")
                    else:
                        active_orders = json_format.MessageToDict(_active_orders).get('items', [])
                        # print(f"main.active_orders: {active_orders}")
                    # Try load last strategy state from saved files
                    last_state = load_last_state(prm.LAST_STATE_FILE)
                    restore_state = bool(last_state)
                    print(f"main.restore_state: {restore_state}")
                    if CANCEL_ALL_ORDERS and active_orders and not prm.LOAD_LAST_STATE:
                        answer = input('Are you want cancel all active order for this pair? Y:\n')
                        if answer.lower() == 'y':
                            restore_state = False
                            try:
                                res = await send_request(
                                    self.stub.CancelAllOrders,
                                    api_pb2.MarketRequest,
                                    symbol=_symbol
                                )
                                cancel_orders = ast.literal_eval(json.loads(res.result))
                                print('Before start was canceled orders:')
                                for i in cancel_orders:
                                    print(f"Order:{i['orderId']}, side:{i['side']},"
                                          f" amount:{i['origQty']}, price:{i['price']}, status:{i['status']}")
                                print(EQUAL_STR)
                            except asyncio.CancelledError:
                                pass  # Task cancellation should not be logged as an error.
                            except grpc.RpcError as ex:
                                status_code = ex.code()
                                print(f"Exception on cancel All order: {status_code.name}, {ex.details()}")
                        else:
                            [exch_orders_ids.append(int(_o['orderId'])) for _o in active_orders]
                # Init section
                loop.create_task(self.get_exchange_info(send_request, _symbol))
                while not self.info_symbol:
                    await asyncio.sleep(0.1)
                # print("\n".join(f"{k}\t{v}" for k, v in self.info_symbol.items()))
                if prm.LOGGING:
                    filters = self.info_symbol.get('filters')
                    for _filter in filters:
                        print(f"{filters.get(_filter).pop('filterType')}: {filters.get(_filter)}")
                # init Strategy class var
                self.base_asset = self.info_symbol.get('baseAsset')
                self.quote_asset = self.info_symbol.get('quoteAsset')
                if prm.MODE in ('T', 'TC'):
                    # region Get and processing Order book
                    _order_book = await self.send_request(
                        self.stub.FetchOrderBook,
                        api_pb2.MarketRequest,
                        symbol=_symbol
                    )
                    self.order_book = order_book_prepare(_order_book)
                    if not self.order_book['bids'] or not self.order_book['asks']:
                        _price = await self.send_request(
                            self.stub.FetchSymbolPriceTicker,
                            api_pb2.MarketRequest,
                            symbol=_symbol
                        )
                        price = json_format.MessageToDict(_price)
                        print(f"Not bids or asks for pair {price.get('symbol')},"
                              f" last known price is {price.get('price')}")
                        amount = self.info_symbol['filters']['lotSize']['minQty']
                        self.order_book['bids'] = self.order_book['bids'] or [[price['price'], amount]]
                        self.order_book['asks'] = self.order_book['asks'] or [[price['price'], amount]]
                    # endregion
                    _ticker = await self.send_request(self.stub.FetchTickerPriceChangeStatistics,
                                                      api_pb2.MarketRequest,
                                                      symbol=_symbol)
                    self.ticker = json_format.MessageToDict(_ticker)
                    # Save first order_book and ticker raw's
                    if prm.MODE == 'TC':
                        ts = int(time.time() * 1000)
                        self.s_order_book['pylist'].append({"key": ts, "row": orjson.dumps(self.order_book)})
                        self.s_ticker['pylist'].append({"key": ts, "row": orjson.dumps(self.ticker)})
                    #
                    loop.create_task(self.save_asset())
                #
                if prm.MODE in ('TC', 'S'):
                    self.session_root = Path(BACKTEST_PATH, f"{self.exchange}_{self.symbol}")
                    self.state_file = Path(self.session_root, "saved_state.json")
                    raw_path = Path(self.session_root, "raw")
                    if prm.MODE == 'TC':
                        BACKTEST_PATH.mkdir(parents=True, exist_ok=True)
                        rmtree(self.session_root, ignore_errors=True)
                        self.session_root.mkdir(parents=True, exist_ok=True)
                        raw_path.mkdir(parents=True, exist_ok=True)
                        #
                        copy(prm.PARAMS, Path(self.session_root, Path(prm.PARAMS).name))
                        self.parquet_declare(raw_path)
            #
            else:
                # Init class atr for reuse in next backtest cycle
                raw_path = Path(self.session_root, "raw")
                self.reset_vars()
            #
            if prm.MODE == 'S':
                self.account.funds.base = {
                    'asset': self.base_asset,
                    'free': prm.AMOUNT_FIRST,
                    'locked': Decimal()
                }
                self.account.funds.quote = {
                    'asset': self.quote_asset,
                    'free': prm.AMOUNT_SECOND,
                    'locked': Decimal()
                }
                self.account.fee_maker = prm.FEE_MAKER
                self.account.fee_taker = prm.FEE_TAKER
                # ticker
                # noinspection PyUnboundLocalVariable
                self.backtest['ticker'] = pq.ParquetFile(Path(raw_path, TICKER_PRKT))
                ticker_first_row = next(self.backtest['ticker'].iter_batches(batch_size=1)).to_pylist()[0]
                self.ticker = orjson.loads(ticker_first_row['row'])
                self.backtest['ticker_index_first'] = ticker_first_row['key']
                # order_book
                self.backtest['order_book'] = pq.ParquetFile(Path(raw_path, ORDER_BOOK_PRKT))
                self.order_book = orjson.loads(
                    next(self.backtest['order_book'].iter_batches(batch_size=1)).to_pylist()[0]['row']
                )
                # candles
                for i in KLINES_INIT:
                    self.backtest[f"candles_{i.value}"] = pq.ParquetFile(Path(raw_path, f"candles_{i.value}.parquet"))

            await self.buffered_funds()
            answer = str()
            restored = True
            if restore_state:
                if last_state.get("command", None) == '"stopped"':
                    input('Saved state was "stopped". Press Enter for continue or Ctrl-Z for Cancel\n')
                    last_state["command"] = 'null'
                if not prm.LOAD_LAST_STATE:
                    answer = input('Restore saved state after restart? Y:\n')
                if prm.LOAD_LAST_STATE or answer.lower() == 'y':
                    self.last_state = last_state
                    try:
                        self.message_log("Load saved state after restart", color=Style.GREEN)
                        # Restore StrategyBase class var
                        self.order_id = json.loads(
                            last_state.pop(MS_ORDER_ID, str(int(datetime.now().strftime("%S%M")) * 1000))
                        )
                        self.start_time_ms = json.loads(
                            last_state.pop('ms_start_time_ms', str(int(time.time() * 1000)))
                        )
                        self.orders = jsonpickle.decode(last_state.pop(MS_ORDERS, '{}'), keys=True)
                        orders_keys = self.orders.keys()
                        for _id in exch_orders_ids:
                            if _id not in orders_keys:
                                _order = next((_o for _o in active_orders if int(_o["orderId"]) == _id))
                                self.orders[_id] = Order(_order)
                                self.message_log(
                                    f"Was restored order {_id}({_order.get('clientOrderId')}) from exchange data",
                                    log_level=LogLevel.WARNING,
                                    color=Style.YELLOW
                                )
                        [self.trades.append(PrivateTrade(trade)) for trade in load_from_csv()]
                        #
                        self.restore_strategy_state(last_state, restore=False)
                        #
                        self.init(check_funds=False)
                        await self.wss_init()
                    except Exception as ex:
                        print(f"Strategy init error: {ex}")
                        restored = False
            if prm.MODE in ('T', 'TC'):
                loop.create_task(self.buffered_orders())
            if not restore_state or (not prm.LOAD_LAST_STATE and answer.lower() != 'y'):
                if prm.MODE in ('T', 'TC'):
                    self.init()
                    input('Press Enter for Start or Ctrl-Z for Cancel\n')
                    print('Waiting for WSS to initialize...')
                    await self.wss_init()
                    while not self.operational_status:
                        await asyncio.sleep(HEARTBEAT)
                    self.start()
                else:
                    # Set initial local time from backtest data
                    self.time_operational['new'] = self.backtest['ticker_index_first'] / 1000
                    self.get_buffered_funds_last_time = self.get_time()
                    self.start_time_ms = int(self.get_time() * 1000)
                    self.cycle_time = datetime.utcnow()
                    #
                    await self.wss_declare()
                    if self.state_file.exists():
                        self.restore_state_before_backtesting()
                        self.init(check_funds=False)
                        self.start_collect = True
                    else:
                        self.init()
                        self.start()
            if restored:
                loop.create_task(self.heartbeat(self.session))
                loop.create_task(save_to_csv())
        except SystemExit as e:
            raise e

    # region AbstractMethod
    @abstractmethod
    def restore_state_before_backtesting_ex(self, *args):
        pass

    @abstractmethod
    def save_strategy_state(self, *args, **kwargs):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def on_new_funds(self, *args):
        pass

    @abstractmethod
    def on_cancel_order_error_string(self, *args):
        pass

    @abstractmethod
    def on_cancel_order_success(self, *args, **kwargs):
        pass

    @abstractmethod
    def on_place_order_error(self, *args):
        pass

    @abstractmethod
    def on_place_order_success(self, *args):
        pass

    @abstractmethod
    def on_balance_update_ex(self, *args):
        pass

    @abstractmethod
    def on_order_update_ex(self, *args):
        pass

    @abstractmethod
    def on_new_ticker(self, *args):
        pass

    @abstractmethod
    def get_sum_profit(self):
        pass

    @abstractmethod
    def get_free_assets(self, *args, **kwargs):
        pass

    @abstractmethod
    def on_new_order_book(self, *args):
        pass

    @abstractmethod
    def restore_strategy_state(self, *args, **kwargs):
        pass

    @abstractmethod
    def start(self, *args):
        pass

    @abstractmethod
    def init(self, *args, **kwargs):
        pass

    # endregion


async def save_to_csv() -> None:
    """
    Header: ["TRADE",
             "transaction_time",
             "side",
             "order_id",
             "client_order_id",
             "trade_id",
             "order_quantity",
             "order_price",
             "cumulative_filled_quantity",
             "quote_asset_transacted",
             "last_executed_quantity",
             "last_executed_price",
             ]
            ['TRANSFER',
             "event_time",
             "asset",
             "balance_delta",
             ]
    :return:
    """
    file_name = Path(LAST_STATE_PATH, f"{prm.ID_EXCHANGE}_{prm.SYMBOL}.csv")
    with open(file_name, mode="a", buffering=1, newline='') as csvfile:
        writer = csv.writer(csvfile)
        while 1:
            writer.writerow(await SAVE_TRADE_QUEUE.get())
            SAVE_TRADE_QUEUE.task_done()


def load_from_csv() -> []:
    file_name = Path(LAST_STATE_PATH, f"{prm.ID_EXCHANGE}_{prm.SYMBOL}.csv")
    trades = []
    if file_name.exists() and file_name.stat().st_size:
        row_count = len(pd.read_csv(file_name, usecols=[0]).index)
        with open(file_name, "r") as csvfile:
            reader = csv.reader(csvfile)
            try:
                [next(reader) for _ in range(row_count - TRADES_LIST_LIMIT)]
            except StopIteration:
                pass
            for row in reader:
                if row[0] in ('TRADE', 'TRADE_BY_MARKET'):
                    trade = {
                        "time": row[1],
                        "isBuyer": row[2] == 'BUY',
                        "isMaker": row[0] == 'TRADE',
                        "orderId": row[3],
                        "id": row[5],
                        "qty": row[10],
                        "price": row[11],
                    }
                    trades.append(trade)
    return trades


def order_book_prepare(_order_book: {}) -> {}:
    order_book = json_format.MessageToDict(_order_book)
    order_book_bids = order_book.pop('bids', [])
    order_book_asks = order_book.pop('asks', [])
    _bids = [json.loads(bid) for bid in order_book_bids]
    _asks = [json.loads(ask) for ask in order_book_asks]
    order_book.update({'bids': _bids})
    order_book.update({'asks': _asks})
    return order_book
