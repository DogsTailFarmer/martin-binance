"""
Functions for managing and saving data to a SQLite database from martin-binance strategy
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.1.3"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import contextlib
import sqlite3
from datetime import datetime
import logging

from martin_binance import DB_FILE

logger = logging.getLogger('logger')


def db_management(exchange) -> None:
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
            logger.error(f"ALTER table t_funds failed: {ex}")
    #
    cursor = conn.cursor()
    # Compliance check t_exchange and EXCHANGE() = exchange() from ms_cfg.toml
    cursor.execute("SELECT id_exchange, name FROM t_exchange")
    row = cursor.fetchall()
    cursor.close()
    row_n = len(row)
    for i, exch in enumerate(exchange):
        if i >= row_n:
            logger.info(f"save_to_db: Add exchange {i}, {exch}")
            try:
                conn.execute("INSERT into t_exchange values(?,?)", (i, exch))
                conn.commit()
            except sqlite3.Error as err:
                logger.error(f"INSERT into t_exchange: {err}")
    #
    try:
        conn.execute('UPDATE t_funds SET active = 0 WHERE active = 1')
        conn.commit()
    except sqlite3.Error as ex:
        logger.error(f"Initialise t_funds failed: {ex}")
    conn.close()


def save_to_db(queue_to_db) -> None:
    connection_analytic = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    # Save data to .db
    data = None
    result = True
    while True:
        with contextlib.suppress(KeyboardInterrupt):
            if result:
                data = queue_to_db.get()
        if data is None or data.get('stop_signal'):
            break
        if data.get('destination') == 't_funds':
            # logger.info("save_to_db: Record row into t_funds")
            try:
                connection_analytic.execute("INSERT INTO t_funds values(\
                                             ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                                             datetime.utcnow(),
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
                                             1))
                connection_analytic.commit()
            except sqlite3.Error as err:
                result = False
                logger.error(f"For save data into t_funds: {err}, retry")
            else:
                result = True
        elif data.get('destination') == 't_orders':
            # logger.info("save_to_db: Record row into t_orders")
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
                                            {'id_exchange': data.get('ID_EXCHANGE'),
                                             'f_currency': data.get('f_currency'),
                                             's_currency': data.get('s_currency'),
                                             'cycle_buy': data.get('cycle_buy'),
                                             'order_buy': data.get('order_buy'),
                                             'order_sell': data.get('order_sell'),
                                             'order_hold': data.get('order_hold')})
                connection_analytic.commit()
            except sqlite3.Error as err:
                logger.error(f"INSERT into t_orders: {err}")
        elif data.get('destination') == 't_funds.active update':
            cursor_analytic = connection_analytic.cursor()
            try:
                cursor_analytic.execute('SELECT 1 FROM t_funds\
                                         WHERE id_exchange =:id_exchange\
                                         AND f_currency =:f_currency\
                                         AND s_currency =:s_currency\
                                         AND active = 1',
                                        {'id_exchange': data.get('ID_EXCHANGE'),
                                         'f_currency': data.get('f_currency'),
                                         's_currency': data.get('s_currency'),
                                         }
                                        )
                row_active = cursor_analytic.fetchone()
                cursor_analytic.close()
            except sqlite3.Error as err:
                cursor_analytic.close()
                row_active = (2,)
                logger.error(f"SELECT from t_funds: {err}")
            if row_active is None:
                # logger.info("save_to_db: UPDATE t_funds set active=1")
                try:
                    connection_analytic.execute('UPDATE t_funds SET active = 1\
                                                 WHERE id=(SELECT max(id) FROM t_funds\
                                                 WHERE id_exchange=:id_exchange\
                                                 AND f_currency=:f_currency\
                                                 AND s_currency=:s_currency)',
                                                {'id_exchange': data.get('ID_EXCHANGE'),
                                                 'f_currency': data.get('f_currency'),
                                                 's_currency': data.get('s_currency'),
                                                 }
                                                )
                    connection_analytic.commit()
                except sqlite3.Error as err:
                    logger.error(f"save_to_db: UPDATE t_funds: {err}")
    connection_analytic.commit()
