"""
martin-binance base class and methods definitions
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.6"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import ast
import asyncio
import csv
import logging
import queue
import os
import random
import sqlite3
import time
import traceback
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from shutil import rmtree, copy, make_archive
from typing import Dict, List

import jsonpickle
import orjson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import ujson as json
from colorama import init as color_init
from tqdm import tqdm

from exchanges_wrapper import martin as mr, Status, GRPCError

import martin_binance.params as prm
from martin_binance import LAST_STATE_PATH, BACKTEST_PATH, HEARTBEAT, KLINES_INIT, EQUAL_STR, ORDER_TIMEOUT
from martin_binance.backtest.exchange_simulator import Account as backTestAccount
from martin_binance.backtest.optimizer import OPTIMIZER, PARAMS_FLOAT
from martin_binance.client import Trade
from martin_binance.lib import Candle, TradingCapabilityManager, Ticker, FundsEntry, OrderBook, Style, \
    any2str, PrivateTrade, Order, convert_from_minute, OrderUpdate, load_file, load_last_state, Klines

if prm.MODE == 'S':
    logger = logging.getLogger('logger_S')
else:
    logger = logging.getLogger('logger')

color_init()

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
CONTROLLED_ASSETS = ['BNB']  # which is not traded, but must be controlled
O_DEC = Decimal()
SAVE_TRADE_QUEUE = asyncio.Queue()


def refresh_t_asset(cursor, key, value, used):
    cursor.execute(
        'DELETE FROM t_asset\
         WHERE id_exchange=:id_exchange\
         AND currency=:currency\
         AND use=:use',
        {'id_exchange': prm.ID_EXCHANGE, 'currency': key, 'use': used}
    )
    cursor.execute(
        'INSERT into t_asset values(?, ?, ?, ?, ?)',
        (prm.ID_EXCHANGE, key, float(value), used, int(time.time()))
    )


class StrategyBase:
    def __init__(self):
        self.session = None
        self.client = None
        self.exchange = str()
        self.symbol = str()
        self.stub = mr.MartinStub
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
        self.tasks = set()
        #
        self.time_operational = {'ts': 0.0, 'diff': 0.0, 'new': 0.0}  # - See get_time()
        self.account = None
        self.get_buffered_funds_last_time = self.get_time()
        self.queue_to_tlg = queue.Queue() if prm.TOKEN and prm.MODE != 'S' else None
        self.status_time = None  # + Last time sending status message
        self.tlg_header = ''  # - Header for Telegram message
        self.start_collect = None
        self.s_mode_break = None
        self.backtest_process = None
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
        self.account = None
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
        self.time_operational = {'ts': 0.0, 'diff': 0.0, 'new': 0.0}

    def update_vars(self, _session):
        self.client = _session.client
        self.stub = _session.stub
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
        return Ticker(self.ticker)

    def get_buffered_funds(self) -> Dict[str, FundsEntry]:
        if self.get_time() - self.get_buffered_funds_last_time > self.rate_limiter:
            self.tasks_manage(self.buffered_funds(print_info=False))
            self.get_buffered_funds_last_time = self.get_time()
        return {self.base_asset: FundsEntry(self.funds[self.base_asset]),
                self.quote_asset: FundsEntry(self.funds[self.quote_asset])}

    def get_buffered_order_book(self) -> OrderBook:
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
            self.tasks_manage(self.transfer2master(symbol, amount))

    def place_limit_order(self, buy: bool, amount: Decimal, price: Decimal) -> int:
        self.order_id += 1
        self.message_log(f"Send order id:{self.order_id} for {'BUY' if buy else 'SELL'}"
                         f" {any2str(amount)} by {any2str(price)} = {any2str(amount * price)}",
                         color=Style.B_YELLOW)
        self.tasks_manage(self.place_limit_order_timeout(self.order_id))
        self.tasks_manage(self.create_limit_order(self.order_id, buy, any2str(amount), any2str(price)))
        if self.exchange == 'huobi':
            time.sleep(0.02)
        return self.order_id

    def cancel_order(self, order_id: int, cancel_all=False) -> None:
        self.tasks_manage(self.cancel_order_timeout(order_id))
        self.tasks_manage(self.cancel_order_call(order_id, cancel_all))

    def message_log(self, msg: str, log_level=logging.INFO, tlg=False, color=Style.WHITE) -> None:
        if prm.LOGGING:
            if tlg and color == Style.WHITE:
                color = Style.B_WHITE
            if log_level >= logging.ERROR:
                tlg = True
                color = Style.B_RED
            color_msg = color + msg + Style.RESET if color else msg
            if log_level >= prm.LOG_LEVEL:
                if prm.MODE in ('T', 'TC'):
                    print(f"{datetime.now().strftime('%d/%m %H:%M:%S')} {color_msg}")
                else:
                    tqdm.write(f"{datetime.fromtimestamp(self.get_time()).strftime('%H:%M:%S.%f')[:-3]} {color_msg}")
            if prm.MODE in ('T', 'TC'):
                logger.log(log_level, msg)
                if tlg and self.queue_to_tlg:
                    msg = self.tlg_header + msg
                    self.status_time = self.get_time()
                    self.queue_to_tlg.put(msg)
        elif log_level >= logging.ERROR:
            logger.log(log_level, msg)

    #
    def order_exist(self, _id) -> bool:
        return bool(self.orders.get(int(_id)))

    def trade_not_exist(self, _order_id: int, _trade_id: int) -> bool:
        return all(
            trade.order_id != _order_id or trade.id != _trade_id for trade in self.trades
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
        _prm_best = {}
        prm_best = {}
        _res = None
        while True:
            await asyncio.sleep(delay)
            try:
                if self.operational_status and self.start_collect and time.time() - ts > prm.SAVE_PERIOD:
                    self.start_collect = False
                    self.session_data_handler()
                    self.reset_backtest_vars()
                    if prm.SELF_OPTIMIZATION and self.command != 'stopped':
                        _ts = datetime.now(timezone.utc).replace(tzinfo=None)
                        storage_name = Path(self.session_root, "_study.db")
                        try:
                            self.backtest_process = await asyncio.create_subprocess_exec(
                                OPTIMIZER,
                                f"{self.exchange}_{self.symbol}",
                                Path(self.session_root, Path(prm.PARAMS).name),
                                str(prm.N_TRIALS),
                                f"sqlite:///{storage_name}",
                                json.dumps(prm_best or _prm_best),
                                f"{prm.ID_EXCHANGE}_{prm.SYMBOL}_S.log",
                                stdout=asyncio.subprocess.PIPE
                            )
                            stdout, _ = await self.backtest_process.communicate()
                        except Exception as ex:
                            self.message_log(f"Backtest process: {ex}", log_level=logging.ERROR)
                        else:
                            _res = stdout.splitlines()
                        if _res:
                            try:
                                prm_best = orjson.loads(_res[0])
                            except orjson.JSONDecodeError:
                                self.message_log(f"Backtest control: response {_res}", log_level=logging.ERROR)
                        #
                        self.backtest_process = None
                        storage_name.replace(storage_name.with_name('study.db'))
                        if prm_best:
                            _prm_best = dict(prm_best)
                            self.message_log(
                                f"Updating parameters from backtest,"
                                f" predicted value {prm_best.pop('_value')} -> {prm_best.pop('new_value')}",
                                color=Style.B_WHITE,
                                tlg=True
                            )
                            for key, value in prm_best.items():
                                self.message_log(f"{key}: {getattr(prm, key)} -> {value}")
                                setattr(
                                    prm, key,
                                    value if isinstance(value, int) or key in PARAMS_FLOAT else Decimal(f"{value}")
                                )
                        l_m = str(
                            datetime.now(timezone.utc).replace(tzinfo=None) - _ts + timedelta(seconds=prm.SAVE_PERIOD)
                        ).rsplit('.')[0]
                        self.message_log(
                            f"Strategy parameters are optimal now. Optimization cycle duration {l_m}",
                            color=Style.B_WHITE,
                            tlg=True
                        )
                        restart = True
                    else:
                        break

                if restart and self.stable_state_backtest():
                    restart = False
                    # Refresh klines init
                    try:
                        for i in KLINES_INIT:
                            res = await self.send_request(self.stub.fetch_klines, mr.FetchKlinesRequest,
                                                          symbol=self.symbol,
                                                          interval=i.value,
                                                          limit=KLINES_LIM)
                            self.klines[i.value] = list(map(json.loads, res.items))
                    except Exception as ex:
                        restart = True
                        self.message_log(f"FetchKlines: {ex}", log_level=logging.WARNING)
                        continue

                    self.parquet_declare(Path(self.session_root, "raw"))
                    # Save current strategy state for backtesting
                    last_state = self.save_strategy_state()
                    self.last_state_update(last_state)
                    with self.state_file.open(mode='w') as outfile:
                        json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                    #
                    self.start_collect = True
                    ts = time.time()
                    self.message_log("Start data collect", tlg=True)
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as err:
                self.message_log(f"Backtest control: {err}", log_level=logging.ERROR)
                self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
                break
        self.message_log("Backtest data collect and optimize session ended", tlg=True)

    def session_data_handler(self):
        """
        Save raw data for back testing and session snapshot for compare.
        """
        # Finalize ticker file
        if _ticker := self.s_ticker['pylist']:
            # noinspection PyArgumentList
            self.s_ticker['writer'].write_batch(
                pa.RecordBatch.from_pylist(mapping=_ticker)
            )
            self.s_ticker['pylist'].clear()
        self.s_ticker['writer'].close()

        # Finalize order_book file
        if _order_book := self.s_order_book['pylist']:
            # noinspection PyArgumentList
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
                # noinspection PyArgumentList
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

        make_archive(str(Path(self.session_root, "raw_bak")), 'zip', self.session_root, 'raw')
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

    def back_test_handler(self):
        # Test result handler
        s_profit = prm.SESSION_RESULT['profit'] = f"{self.get_sum_profit()}"
        s_free = prm.SESSION_RESULT['free'] = f"{self.get_free_assets(mode='free', backtest=True)[2]}"
        if prm.LOGGING:
            print(f"Session profit: {s_profit}, free: {s_free}, total: {float(s_profit) + float(s_free)}")
            test_time = datetime.now(timezone.utc).replace(tzinfo=None) - self.cycle_time
            original_time = (self.backtest['ticker_index_last'] - self.backtest['ticker_index_first']) / 1000
            original_time = timedelta(seconds=original_time)
            print(f"Original time: {original_time}, test time: {test_time}, x = {original_time / test_time:.2f}")
        if prm.SAVE_DS:
            self._back_test_handler_ext()

        self.session.channel.close()
        self.task_cancel()
        asyncio.get_event_loop().stop()

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

    async def heartbeat(self, _session):
        # print(f"tik-tak:' {int(time.time() * 1000)}")
        last_exec_time = time.time()
        while True:
            try:
                self.refresh_scheduler()
                if prm.MODE in ('T', 'TC'):
                    last_state = self.save_strategy_state()
                    self.last_state_update(last_state)
                    # print(f"heartbeat.last_state: {last_state}")
                    if prm.LAST_STATE_FILE.exists():
                        prm.LAST_STATE_FILE.replace(prm.LAST_STATE_FILE.with_suffix('.prev'))
                    with prm.LAST_STATE_FILE.open(mode='w') as outfile:
                        json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                    #
                    update_max_queue_size = False
                    if (
                        not self.wss_fire_up
                        and self.operational_status
                        and (time.time() - last_exec_time > HEARTBEAT * 10)
                    ):
                        last_exec_time = time.time()
                        try:
                            res = await self.send_request(
                                self.stub.check_stream,
                                mr.MarketRequest,
                                symbol=self.symbol
                            )
                        except UserWarning as ex:
                            self.wss_fire_up = True
                            self.message_log(f"{ex}", log_level=logging.WARNING)
                        except Exception as ex:
                            self.message_log(f"Exception on check WSS: {ex}", log_level=logging.ERROR)
                        else:
                            if not res.success:
                                self.message_log(f"Not active WSS for {self.symbol} on {self.exchange},"
                                                 f" restart request sent", log_level=logging.WARNING)
                                update_max_queue_size = True
                                self.wss_fire_up = True
                        finally:
                            if self.wss_fire_up:
                                self.operational_status = False
                    #
                    if self.wss_fire_up:
                        try:
                            if await self.session.get_client():
                                self.update_vars(self.session)
                                await self.send_request(
                                    self.stub.stop_stream,
                                    mr.MarketRequest,
                                    symbol=self.symbol
                                )
                                await self.wss_init(update_max_queue_size=update_max_queue_size)
                        except Exception as ex:
                            self.message_log(f"Exception on fire up WSS: {ex}", log_level=logging.WARNING)
                            self.message_log(traceback.format_exc(), log_level=logging.DEBUG)
                            self.wss_fire_up = True
                await asyncio.sleep(HEARTBEAT)
            except (KeyboardInterrupt, asyncio.CancelledError):
                break

    async def save_asset(self):
        """
        Update account asset list and value in t_asset
        """
        connection_analytic = None
        balances = []
        while connection_analytic is None:
            connection_analytic = self.connection_analytic
            await asyncio.sleep(HEARTBEAT)
        delay = 600  # 10 min
        max_use_update = 25 * 60  # 25 min if the row has not been updated that the instance is down
        while True:
            if not self.operational_status:
                await asyncio.sleep(HEARTBEAT * 30)
                continue
            try:
                res = await self.send_request(self.stub.fetch_account_information, mr.OpenClientConnectionId)
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as _ex:
                self.message_log(f"Exception save_asset: {_ex}", log_level=logging.WARNING)
            else:
                if res:
                    balances = list(map(json.loads, res.items))
                # Refresh actual balance
                try:
                    balance_f = next(item for item in balances if item["asset"] == self.base_asset)
                except StopIteration:
                    balance_f = {'asset': self.base_asset, 'free': '0.0', 'locked': '0.0'}
                try:
                    balance_s = next(item for item in balances if item["asset"] == self.quote_asset)
                except StopIteration:
                    balance_s = {'asset': self.base_asset, 'free': '0.0', 'locked': '0.0'}
                self.funds = {
                    self.base_asset: {'free': balance_f['free'], 'locked': balance_f['locked']},
                    self.quote_asset: {'free': balance_s['free'], 'locked': balance_s['locked']}
                }
                # Get asset balances from Funding Wallet
                funding_wallet = []
                assets_fw = {}
                if self.exchange not in ('bitfinex', 'huobi'):
                    try:
                        res = await self.send_request(self.stub.fetch_funding_wallet, mr.FetchFundingWalletRequest)
                    except (asyncio.CancelledError, KeyboardInterrupt):
                        break
                    except Exception as _ex:
                        logger.warning(f"FetchFundingWallet: {_ex}")
                    else:
                        funding_wallet = list(map(json.loads, res.items))
                    for fw in funding_wallet:
                        assets_fw[fw['asset']] = Decimal(fw['free']) + Decimal(fw['locked']) + Decimal(fw['freeze'])
                # Create list of cumulative asset from SPOT and Funding wallet
                assets = {}
                controlled_assets = [self.base_asset, self.quote_asset] + CONTROLLED_ASSETS
                for balance in balances:
                    if self.exchange != 'bitfinex':
                        total = assets_fw.pop(balance['asset'], O_DEC)
                    else:
                        total = Decimal('0.0')
                    if balance['asset'] in controlled_assets or prm.GRID_ONLY:
                        total += Decimal(balance['free']) + Decimal(balance['locked'])
                    assets[balance['asset']] = float(total)

                cursor = connection_analytic.cursor()
                try:
                    cursor.execute('BEGIN')
                    cursor.execute(
                        'DELETE FROM t_asset WHERE timestamp<:timestamp',
                        {'timestamp': time.time() - max_use_update}
                    )

                    for key, value in assets_fw.items():
                        refresh_t_asset(cursor, key, value, used=0)

                    for key, value in assets.items():
                        if prm.GRID_ONLY:
                            refresh_t_asset(cursor, key, value, used=0)
                        elif key in controlled_assets:
                            refresh_t_asset(cursor, key, value, used=1)

                    cursor.execute('COMMIT')
                    cursor.close()
                except sqlite3.Error as err:
                    cursor.execute('ROLLBACK')
                    cursor.close()
                    self.message_log(f"Refresh t_asset: {err}", log_level=logging.WARNING)
            await asyncio.sleep(delay)

    async def ask_exit(self):
        self.message_log("Got signal for exit", color=Style.MAGENTA)
        self.operational_status = False
        self.s_mode_break = True
        if self.backtest_process:
            self.backtest_process.terminate()
            self.message_log("Backtest process was terminated", color=Style.GREEN)
        await asyncio.sleep(HEARTBEAT)
        if prm.MODE in ('T', 'TC'):
            try:
                await self.send_request(self.stub.stop_stream, mr.MarketRequest, symbol=self.symbol)
            except Exception as ex:
                self.message_log(f"ask_exit: {ex}", log_level=logging.WARNING)

            self.session.channel.close()
            self.task_cancel()

            if prm.MODE == 'TC' and self.start_collect:
                # Save stream data for backtesting
                self.start_collect = False
                self.session_data_handler()

            if prm.LAST_STATE_FILE.exists():
                print(f"Current state saved into {prm.LAST_STATE_FILE}")

            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
            if prm.LOGGING:
                print(f"Cancelling {len(tasks)} outstanding tasks")

            self.stop()

    async def fetch_order(self, _id: int, _client_order_id: str = None, _filled_update_call=False):
        try:
            res = await self.send_request(
                self.stub.fetch_order, mr.FetchOrderRequest,
                symbol=self.symbol,
                order_id=_id,
                client_order_id=_client_order_id,
                filled_update_call=_filled_update_call
            )
            result = res.to_pydict()
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except Exception as _ex:
            self.message_log(f"Exception in fetch_order: {_ex}", log_level=logging.ERROR)
            return {}
        else:
            self.message_log(f"For order {_id}({_client_order_id}) fetched status is {result.get('status')}",
                             log_level=logging.INFO, color=Style.GREEN)
            if result:
                return result
            self.message_log(f"Can't get status for order {_id}({_client_order_id})",
                             log_level=logging.WARNING)
            return {}

    async def on_funds_update(self):
        if prm.MODE in ('T', 'TC'):
            try:
                async for _funds in self.for_request(
                        self.stub.on_funds_update, mr.OnFundsUpdateRequest,
                        symbol=self.symbol,
                        base_asset=self.base_asset,
                        quote_asset=self.quote_asset
                ):
                    funds = json.loads(_funds.event)
                    if funds.get(self.base_asset) or funds.get(self.quote_asset):
                        self.on_funds_update_handler(funds)
            except Exception as ex:
                self.message_log(f"Exception on WSS, on_funds_update loop closed: {ex}", log_level=logging.WARNING)
                self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
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
            await asyncio.sleep(0.010)

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

                if self.s_mode_break:
                    break
            else:
                continue
            break

        if ticker:
            self.backtest['ticker_index_last'] = index_prev * 1000

    async def aiter_candles(self, _klines: {str: Klines}, _i: str):
        self.s_mode_break = None
        async for row in self.loop_ds(self.backtest[f"candles_{_i}"]):
            _klines.get(_i).refresh(row)
            if self.s_mode_break:
                break
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
                        res = await self.send_request(
                            self.stub.cancel_all_orders,
                            mr.MarketRequest,
                            symbol=self.symbol
                        )
                        if res:
                            for v in ast.literal_eval(json.loads(res.result)):
                                self.bulk_orders_cancel.update({v['orderId']: v})
                    result = self.bulk_orders_cancel.pop(_id, None)
                else:
                    res = await self.send_request(
                        self.stub.cancel_order,
                        mr.CancelOrderRequest,
                        symbol=self.symbol,
                        order_id=_id
                    )
                    result = res.to_pydict()
            else:
                result = self.account.cancel_order(order_id=_id, ts=int(self.get_time() * 1000))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except GRPCError as ex:
            _fetch_order = True
            self.message_log(f"Exception on cancel order {_id}: {ex.status.name}, {ex.message}")
        except UserWarning as ex:
            _fetch_order = True
            self.message_log(f"Exception on cancel order call for {_id}: {ex}", log_level=logging.WARNING)
        except Exception as ex:
            _fetch_order = True
            self.message_log(f"Exception on cancel order call for {_id}: {ex}", log_level=logging.ERROR)
            self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
        else:
            # print(f"cancel_order_call.result: {result}")
            # Remove from orders lists
            if result and result.get('status') == 'CANCELED':
                await self.cancel_order_handler(_id, cancel_all)
            else:
                self.message_log(f"Cancel order {_id}: Warning, not result getting")
                _fetch_order = True
        finally:
            if prm.MODE in ('T', 'TC') and _fetch_order:
                res = await self.fetch_order(_id, _filled_update_call=True)
                if res.get('status') in ('CANCELED', 'EXPIRED_IN_MATCH'):
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
        # await asyncio.sleep(0)

    async def transfer2master(self, symbol: str, amount: str):
        try:
            res = await self.send_request(
                self.stub.transfer_to_master,
                mr.MarketRequest,
                symbol=symbol,
                amount=amount
            )
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except GRPCError as ex:
            status_code = ex.status
            self.message_log(f"Exception transfer {symbol} to main account: {status_code.name}, {ex.message}")
        except Exception as _ex:
            self.message_log(f"Exception transfer {symbol} to main account: {_ex}")
        else:
            if res.success:
                self.message_log(f"Sent {amount} {symbol} to main account", log_level=logging.INFO)
            else:
                self.message_log(f"Not sent {amount} {symbol} to main account\n,{res.result}",
                                 log_level=logging.WARNING)

    async def buffered_funds(self, print_info: bool = True):
        try:
            if prm.MODE in ('T', 'TC'):
                res = await self.send_request(self.stub.fetch_account_information, mr.OpenClientConnectionId)
                balances = list(map(json.loads, res.items))
            else:
                balances = self.account.funds.get_funds()
        except asyncio.CancelledError:
            pass
        except UserWarning as _ex:
            self.message_log(f"UserWarning: {_ex}", log_level=logging.DEBUG)
        except Exception as _ex:
            self.message_log(f"Exception buffered_funds: {_ex}", log_level=logging.WARNING)
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
        while True:
            try:
                _exchange_info_symbol = await _request(self.stub.fetch_exchange_info_symbol,
                                                       mr.MarketRequest,
                                                       symbol=_symbol)
            except asyncio.CancelledError:
                pass  # Task cancellation should not be logged as an error
            except Exception as _ex:
                self.message_log(f"Exception get_exchange_info: {_ex}")
            else:
                self.info_symbol = _exchange_info_symbol.to_pydict()
                self.tcm = TradingCapabilityManager(self.info_symbol, prm.PRICE_LIMIT_RULES)
                if prm.MODE == 'S':
                    break
            await asyncio.sleep(600)

    async def buffered_candle(self):
        Klines.klines_lim = KLINES_LIM
        klines = {}
        klines_from_file = {}
        kline = []
        if prm.MODE == 'S':
            klines_from_file = json.load(open(Path(self.session_root, "raw/klines.json")))
        for i in KLINES_INIT:
            if prm.MODE in ('T', 'TC'):
                try:
                    res = await self.send_request(
                        self.stub.fetch_klines, mr.FetchKlinesRequest,
                        symbol=self.symbol,
                        interval=i.value,
                        limit=KLINES_LIM
                    )
                except Exception as ex:
                    self.message_log(f"FetchKlines: {ex}", log_level=logging.WARNING)
                else:
                    if res:
                        kline = list(map(json.loads, res.items))
                        if prm.MODE == 'TC' and (self.start_collect or self.start_collect is None):
                            self.klines[i.value] = kline
            else:
                kline = klines_from_file.get(i.value, [])

            kline_i = Klines(i.value)
            for candle in kline:
                kline_i.refresh(candle)
            klines[i.value] = kline_i

        if len(klines) == len(KLINES_INIT):
            self.tasks_manage(self.on_klines_update(klines), name='wss')
        else:
            self.message_log("Init buffered candle failed. try one else...", log_level=logging.WARNING)
            await asyncio.sleep(random.uniform(1, 5))
            self.wss_fire_up = True

    async def on_klines_update(self, _klines: {str: Klines}):
        _intervals = list(_klines.keys())
        if prm.MODE in ('T', 'TC'):
            try:
                async for res in self.for_request(self.stub.on_klines_update, mr.FetchKlinesRequest,
                                                  symbol=self.symbol,
                                                  interval=json.dumps(_intervals)):
                    candle = json.loads(res.candle)
                    _klines.get(res.interval).refresh(candle)
                    if prm.MODE == 'TC' and (self.start_collect or self.start_collect is None):
                        if len(self.candles[f"pylist_{res.interval}"]) > PYARROW_BATCH_BUFFER_SIZE:
                            # noinspection PyArgumentList
                            self.candles[f"writer_{res.interval}"].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.candles[f"pylist_{res.interval}"])
                            )
                            self.candles[f"pylist_{res.interval}"].clear()

                        self.candles[f"pylist_{res.interval}"].append(
                            {"key": int(time.time() * 1000), "row": orjson.dumps(candle)}
                        )
            except Exception as ex:
                self.message_log(f"Exception on WSS, on_klines_update loop closed: {ex}", log_level=logging.WARNING)
                self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
                self.wss_fire_up = True
        else:
            for i in _intervals:
                self.tasks_manage(self.aiter_candles(_klines, i), name='wss')

    async def create_limit_order(self, _id: int, buy: bool, amount: str, price: str) -> None:
        self.wait_order_id.append(_id)
        _fetch_order = False
        try:
            if prm.MODE in ('T', 'TC'):
                ts = time.time()
                res = await self.send_request(
                    self.stub.create_limit_order, mr.CreateLimitOrderRequest,
                    symbol=self.symbol,
                    buy_side=buy,
                    quantity=amount,
                    price=price,
                    new_client_order_id=_id
                )
                result = res.to_pydict()
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
        except GRPCError as ex:
            status_code = ex.status
            if status_code == Status.FAILED_PRECONDITION:
                if _id in self.wait_order_id:
                    # Supress call strategy handler
                    self.wait_order_id.remove(_id)
            else:
                _fetch_order = True
            self.on_place_order_error(_id, f"{status_code.name}, {ex.message}")
        except Exception as _ex:
            _fetch_order = True
            self.message_log(f"Exception creating order {_id}: {_ex}")
        else:
            if result:
                await self.create_order_handler(_id, result)
            else:
                _fetch_order = True
        finally:
            if prm.MODE in ('T', 'TC') and _fetch_order:
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
            async for res in self.for_request(self.stub.on_balance_update, mr.MarketRequest, symbol=self.symbol):
                _res = json.loads(res.event)
                await SAVE_TRADE_QUEUE.put(
                    ['TRANSFER',
                     _res["event_time"],
                     _res["asset"],
                     _res["balance_delta"]]
                )
                self.on_balance_update_ex(_res)
        except Exception as ex:
            self.message_log(f"Exception on WSS, on_balance_update loop closed: {ex}", log_level=logging.WARNING)
            self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
            self.wss_fire_up = True

    async def on_order_update(self):
        try:
            async for event in self.for_request(self.stub.on_order_update, mr.MarketRequest, symbol=self.symbol):
                # Only for registered orders on own pair
                ed = json.loads(event.result)
                await self.on_order_update_handler(ed)
        except Exception as ex:
            self.message_log(f"Exception on WSS, on_order_update loop closed: {ex}", log_level=logging.WARNING)
            self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
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
            if prm.MODE in ('T', 'TC'):
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

        if prm.MODE == 'TC' and self.start_collect and self.s_ticker['pylist']:
            s_tic = self.s_ticker['pylist'].pop()
            s_tic_row = orjson.loads(s_tic['row'])
            s_tic_row['lastPrice'] = ed['last_executed_price']
            if ed['order_status'] == 'PARTIALLY_FILLED':
                s_tic_row['Qty'] = ed['last_executed_quantity']
            s_tic['row'] = orjson.dumps(s_tic_row)
            self.s_ticker['pylist'].append(s_tic)
            if prm.SAVE_DS:
                self.open_orders_snapshot()

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
            self.message_log(f"Order: {ed['order_id']} was missed partially filling event", log_level=logging.INFO)
            ed['order_status'] = 'PARTIALLY_FILLED'
        self.on_order_update_ex(OrderUpdate(ed, self.trades))

    async def on_ticker_update(self):
        """
        row = {'openPrice': '26923.97000000', 'lastPrice': '26882.51000000', 'closeTime': 1684572464013}
        :return:
        """
        if prm.MODE in ('T', 'TC'):
            try:
                async for _ticker in self.for_request(
                        self.stub.on_ticker_update,
                        mr.MarketRequest,
                        symbol=self.symbol
                ):
                    self.ticker = _ticker.to_pydict()
                    self.on_new_ticker(Ticker(self.ticker))
                    #
                    if prm.MODE == 'TC' and self.start_collect:
                        ts = int(time.time() * 1000)
                        self.ticker |= {'delay': self.delay_ordering_s, 'Qty': "0"}
                        if len(self.s_ticker['pylist']) > PYARROW_BATCH_BUFFER_SIZE:
                            # noinspection PyArgumentList
                            self.s_ticker['writer'].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.s_ticker['pylist'])
                            )
                            self.s_ticker['pylist'].clear()
                        self.s_ticker['pylist'].append({"key": ts, "row": orjson.dumps(self.ticker)})
                        if prm.SAVE_DS:
                            self.open_orders_snapshot(ts=ts)
            except Exception as ex:
                self.message_log(f"Exception on WSS, on_ticker_update loop closed: {ex}", log_level=logging.WARNING)
                self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
                self.wss_fire_up = True
        else:
            if prm.LOGGING:
                pbar = tqdm(total=self.backtest['ticker'].metadata.num_rows)
            self.s_mode_break = None
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
                if self.s_mode_break:
                    break
            if prm.LOGGING:
                pbar.close()
            self.message_log("Backtest *** ticker *** timeSeries ended")
            self.s_mode_break = True
            self.back_test_handler()

    async def on_order_book_update(self):
        if prm.MODE in ('T', 'TC'):
            try:
                async for _order_book in self.for_request(
                        self.stub.on_order_book_update,
                        mr.MarketRequest,
                        symbol=self.symbol
                ):
                    self.order_book = order_book_prepare(_order_book)
                    self.on_new_order_book(OrderBook(self.order_book))
                    if prm.MODE == 'TC' and self.start_collect:
                        self.order_book['bids'] = self.order_book['bids'][:1]
                        self.order_book['asks'] = self.order_book['asks'][:1]
                        if len(self.s_order_book['pylist']) > PYARROW_BATCH_BUFFER_SIZE:
                            # noinspection PyArgumentList
                            self.s_order_book['writer'].write_batch(
                                pa.RecordBatch.from_pylist(mapping=self.s_order_book['pylist'])
                            )
                            self.s_order_book['pylist'].clear()
                        self.s_order_book['pylist'].append(
                            {"key": int(time.time() * 1000), "row": orjson.dumps(self.order_book)}
                        )
            except Exception as ex:
                self.message_log(f"Exception on WSS, on_order_book_update loop closed: {ex}", log_level=logging.WARNING)
                self.message_log(f"Exception traceback: {traceback.format_exc()}", log_level=logging.DEBUG)
                self.wss_fire_up = True
        else:
            self.s_mode_break = None
            async for row in self.loop_ds(self.backtest['order_book']):
                self.order_book = row
                self.on_new_order_book(OrderBook(row))
                if self.s_mode_break:
                    break
            self.message_log("Backtest *** order_book *** timeSeries ended")

    async def buffered_orders(self):
        exch_orders = []
        diff_id = set()
        restore = False
        while True:
            if not self.operational_status:
                await asyncio.sleep(HEARTBEAT)
                continue
            try:
                _orders = await self.send_request(self.stub.fetch_open_orders, mr.MarketRequest, symbol=self.symbol)
                if _orders is None:
                    raise UserWarning("Can't fetch open orders")

                self.rate_limiter = max(self.rate_limiter, _orders.rate_limiter)

                orders = list(map(json.loads, _orders.orders))
                [exch_orders.append(int(_o['orderId'])) for _o in orders]

                if restore:
                    self.message_log("Restore saved state after lost connection to host", color=Style.GREEN)

                if self.last_state:
                    self.message_log("Restore saved state after restart", color=Style.GREEN, tlg=True)
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
                                     f" checking it", log_level=logging.WARNING, tlg=False)
                    for _id in diff_id:
                        res = await self.fetch_order(_id, _filled_update_call=True)
                        if res.get('status') in ('CANCELED', 'EXPIRED_IN_MATCH'):
                            await self.cancel_order_handler(_id, cancel_all=False)

                if self.last_state and prm.MODE == 'TC':
                    last_state = self.save_strategy_state()
                    self.last_state_update(last_state)
                    with self.state_file.open(mode='w') as outfile:
                        json.dump(last_state, outfile, sort_keys=True, indent=4, ensure_ascii=False)
                    self.start_collect = True
                exch_orders.clear()
                diff_id.clear()
                self.last_state = None
                restore = False

            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except UserWarning as ex_2:
                self.message_log(f"Exception buffered_orders 2: {ex_2}", log_level=logging.WARNING)
                restore = True
            except GRPCError as ex_3:
                status_code = ex_3.status
                self.message_log(f"Exception buffered_orders 3: {status_code.name}, {ex_3.message}",
                                 log_level=logging.WARNING, color=Style.B_RED, tlg=True)
                if status_code == Status.RESOURCE_EXHAUSTED:
                    # Decrease requests frequency
                    self.rate_limiter += HEARTBEAT
                    self.message_log(f"RATE_LIMITER set to {self.rate_limiter}s", log_level=logging.WARNING)
                    await asyncio.sleep(ORDER_TIMEOUT)
                    try:
                        await self.send_request(self.stub.reset_rate_limit, mr.OpenClientConnectionId,
                                                rate_limiter=self.rate_limiter)
                    except Exception as ex_4:
                        self.message_log(f"Exception buffered_orders 4:ResetRateLimit: {ex_4}",
                                         log_level=logging.WARNING)
                else:
                    restore = True
            except Exception as ex_5:
                self.message_log(f"Exception buffered_orders 5: {ex_5}", log_level=logging.ERROR)
                self.message_log(traceback.format_exc(), log_level=logging.DEBUG)
                restore = True
            await asyncio.sleep(self.rate_limiter)

    async def wait_wss_init(self):
        while not self.operational_status:
            await asyncio.sleep(HEARTBEAT)
            try:
                res = await self.send_request(self.stub.check_stream, mr.MarketRequest, symbol=self.symbol)
            except Exception as ex_1:
                self.message_log(f"Exception on Check WSS: {ex_1}", log_level=logging.WARNING)
            else:
                if res.success:
                    self.operational_status = True

    def tasks_manage(self, coro, name=None, add_done_callback=True):
        _t = asyncio.create_task(coro, name=name)
        self.tasks.add(_t)
        if add_done_callback:
            _t.add_done_callback(self.tasks.discard)

    async def wss_declare(self):
        # Market stream
        self.tasks_manage(self.on_ticker_update(), name='wss')
        await self.buffered_candle()
        self.tasks_manage(self.on_order_book_update(), name='wss')
        if prm.MODE in ('T', 'TC'):
            # User Stream
            self.tasks_manage(self.on_funds_update(), name='wss')
            self.tasks_manage(self.on_order_update(), name='wss')
            self.tasks_manage(self.on_balance_update(), name='wss')

    async def wss_init(self, update_max_queue_size=False):
        if self.client_id:
            self.message_log(f"Init WSS, client_id: {self.client_id}")
            self.task_cancel()
            await self.wss_declare()
            # WSS start
            '''
            market_stream_count=5
            These values directly depend on the number of market ws streams used in the strategy and declared above
            '''
            try:
                await self.send_request(self.stub.start_stream,
                                        mr.StartStreamRequest,
                                        symbol=self.symbol,
                                        market_stream_count=5,
                                        update_max_queue_size=update_max_queue_size)
            except UserWarning:
                self.message_log("Start WSS failed, retry", log_level=logging.WARNING)
                self.wss_fire_up = True
            else:
                self.wss_fire_up = False
                await self.wait_wss_init()
        else:
            self.message_log("Init WSS failed, retry", log_level=logging.WARNING)
            await asyncio.sleep(random.randint(HEARTBEAT, HEARTBEAT * 5))
            self.wss_fire_up = True

    def task_cancel(self):
        [task.cancel() for task in self.tasks if not task.done() and task.get_name() == 'wss']

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
                            self.stub.fetch_open_orders,
                            mr.MarketRequest,
                            symbol=_symbol
                        )
                    except Exception as ex:
                        print(f"Can't get active orders: {ex}")
                    else:
                        active_orders = list(map(json.loads, _active_orders.orders))
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
                                    self.stub.cancel_all_orders,
                                    mr.MarketRequest,
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
                            except GRPCError as ex:
                                print(f"Exception on cancel All order: {ex.status.name}, {ex.message}")
                        else:
                            [exch_orders_ids.append(int(_o['orderId'])) for _o in active_orders]
                # Init section
                self.tasks_manage(self.get_exchange_info(send_request, _symbol))
                while not self.info_symbol:
                    await asyncio.sleep(0.1)
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
                        self.stub.fetch_order_book,
                        mr.MarketRequest,
                        symbol=_symbol
                    )
                    self.order_book = order_book_prepare(_order_book)
                    if not self.order_book['bids'] or not self.order_book['asks']:
                        _price = await self.send_request(
                            self.stub.fetch_symbol_price_ticker,
                            mr.MarketRequest,
                            symbol=_symbol
                        )
                        price = _price.to_pydict()
                        print(f"Not bids or asks for pair {price.get('symbol')},"
                              f" last known price is {price.get('price')}")
                        amount = self.info_symbol['filters']['lotSize']['minQty']
                        self.order_book['bids'] = self.order_book['bids'] or [[price['price'], amount]]
                        self.order_book['asks'] = self.order_book['asks'] or [[price['price'], amount]]
                    # endregion
                    _ticker = await self.send_request(
                        self.stub.fetch_ticker_price_change_statistics,
                        mr.MarketRequest,
                        symbol=_symbol
                    )
                    self.ticker = _ticker.to_pydict()
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
                self.reset_vars_ex()
            #
            if prm.MODE == 'S':
                self.account = backTestAccount(prm.SAVE_DS)
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

            if restore_state:
                if last_state.get("command", None) == '"stopped"':
                    input('Saved state was "stopped". Press Enter for continue or Ctrl-Z for Cancel\n')
                    last_state["command"] = 'null'
                if not prm.LOAD_LAST_STATE:
                    answer = input('Restore saved state after restart? Y:\n')
                if prm.LOAD_LAST_STATE or answer.lower() == 'y':
                    self.message_log("Load saved state after restart", color=Style.GREEN)
                    self.last_state = last_state
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
                                log_level=logging.WARNING,
                                color=Style.YELLOW
                            )
                    [self.trades.append(PrivateTrade(trade)) for trade in load_from_csv()]
                    #
                    self.restore_strategy_state(strategy_state=last_state, restore=False)
                    #
                    self.init(check_funds=False)
                else:
                    restore_state = False

            if not restore_state:
                if prm.MODE in ('T', 'TC'):
                    self.init()
                    input('Press Enter for Start or Ctrl-Z for Cancel\n')
                else:
                    # Set initial local time from backtest data
                    self.time_operational['new'] = self.backtest['ticker_index_first'] / 1000
                    self.get_buffered_funds_last_time = self.get_time()
                    self.start_time_ms = int(self.get_time() * 1000)
                    self.cycle_time = datetime.now(timezone.utc).replace(tzinfo=None)
                    #
                    await self.wss_declare()
                    if self.state_file.exists():
                        self.restore_state_before_backtesting()
                        self.init(check_funds=False)
                        self.start_collect = True
                    else:
                        self.init()
                        self.start()

            if prm.MODE in ('T', 'TC'):
                await self.wss_init()
                self.tasks_manage(save_to_csv())
                self.tasks_manage(self.buffered_orders(), add_done_callback=False)
                if self.session.client.real_market:
                    self.tasks_manage(self.save_asset(), add_done_callback=False)
                if prm.MODE == 'TC':
                    self.tasks_manage(self.backtest_control(), add_done_callback=False)
                if not restore_state:
                    self.start()

            self.tasks_manage(self.heartbeat(self.session), add_done_callback=False)

        except (KeyboardInterrupt, SystemExit):
            # noinspection PyProtectedMember, PyUnresolvedReferences
            os._exit(1)

    # region AbstractMethod
    @abstractmethod
    def restore_state_before_backtesting_ex(self, *args):
        raise NotImplementedError

    @abstractmethod
    def save_strategy_state(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @abstractmethod
    def on_new_funds(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_cancel_order_error_string(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_cancel_order_success(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def on_place_order_error(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_place_order_success(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_balance_update_ex(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_order_update_ex(self, *args):
        raise NotImplementedError

    @abstractmethod
    def on_new_ticker(self, *args):
        raise NotImplementedError

    @abstractmethod
    def get_sum_profit(self):
        raise NotImplementedError

    @abstractmethod
    def get_free_assets(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def on_new_order_book(self, *args):
        raise NotImplementedError

    @abstractmethod
    def restore_strategy_state(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def start(self, *args):
        raise NotImplementedError

    @abstractmethod
    def init(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def reset_vars_ex(self):
        raise NotImplementedError

    @abstractmethod
    def refresh_scheduler(self):
        raise NotImplementedError

    @abstractmethod
    def stable_state_backtest(self):
        raise NotImplementedError

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
        while True:
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


def order_book_prepare(_order_book) -> {}:
    order_book = _order_book.to_pydict()
    order_book['bids'] = list(map(json.loads, order_book['bids']))
    order_book['asks'] = list(map(json.loads, order_book['asks']))
    return order_book
