"""
Functions for managing and saving data to a SQLite database from martin-binance strategy
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.1.8"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import contextlib
import aiosqlite
from aiosqlite import Error as SqliteError
from datetime import datetime, timezone
import logging

from martin_binance import DB_FILE

logger = logging.getLogger('logger')


async def db_management(exchange) -> None:
    async with aiosqlite.connect(DB_FILE) as db_connect:
        try:
            await db_connect.execute("DELETE FROM t_orders")
        except SqliteError as ex:
            logger.error(f"DELETE from table t_orders failed: {ex}")
        else:
            await db_connect.commit()
        # Compliance check t_exchange and EXCHANGE() = exchange() from ms_cfg.toml
        try:
            cursor = await db_connect.execute("SELECT id_exchange, name FROM t_exchange")
        except SqliteError as ex:
            logger.error(f"SELECT from t_exchange: {ex}")
        else:
            rows = await cursor.fetchall()
            row_n = len(rows)
            for i, exch in enumerate(exchange):
                if i >= row_n:
                    logger.info(f"save_to_db: Add exchange {i}, {exch}")
                    try:
                        await db_connect.execute("INSERT into t_exchange values(?,?)", (i, exch))
                    except SqliteError as ex:
                        logger.error(f"INSERT into t_exchange: {ex}")
                    else:
                        await db_connect.commit()


async def save_to_db(queue_to_db) -> None:
    # Save data to .db
    data = None
    result = True
    async with aiosqlite.connect(DB_FILE) as db_connect:
        while True:
            with contextlib.suppress(KeyboardInterrupt):
                if result:
                    data = await queue_to_db.get()
            if data is None or data.get('stop_signal'):
                break
            if data.get('destination') == 't_funds':
                # logger.info("save_to_db: Record row into t_funds")
                try:
                    await db_connect.execute(
                        "INSERT INTO t_funds values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (data.get('ID_EXCHANGE'),
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
                         datetime.now(timezone.utc).replace(tzinfo=None),
                         float(data.get('PRICE_SHIFT')),
                         float(data.get('PROFIT')),
                         float(data.get('over_price')),
                         data.get('order_q'),
                         float(data.get('MARTIN')),
                         data.get('LINEAR_GRID_K'),
                         data.get('ADAPTIVE_TRADE_CONDITION'),
                         data.get('KBB'),
                         1,
                         data.get('cycle_time'),
                         0)
                    )
                except SqliteError as err:
                    result = False
                    logger.error(f"For save data into t_funds: {err}, retry")
                else:
                    await db_connect.commit()
                    result = True
            elif data.get('destination') == 't_orders':
                # logger.info("save_to_db: Record row into t_orders")
                try:
                    await db_connect.execute(
                        "INSERT INTO t_orders VALUES(:id_exchange,\
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
                        {'id_exchange': data.get('ID_EXCHANGE'),
                         'f_currency': data.get('f_currency'),
                         's_currency': data.get('s_currency'),
                         'cycle_buy': data.get('cycle_buy'),
                         'order_buy': data.get('order_buy'),
                         'order_sell': data.get('order_sell'),
                         'order_hold': data.get('order_hold')}
                    )
                except SqliteError as err:
                    logger.error(f"INSERT into t_orders: {err}")
                else:
                    await db_connect.commit()

            queue_to_db.task_done()
