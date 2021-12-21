#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Cyclic grid strategy based on martingale
# See README.md for detail
####################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.0rc2"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
"""
##################################################################
Disclaimer

All risks and possible losses associated with use of this strategy lie with you.
Strongly recommended that you test the strategy in the demo mode before using real bidding.
##################################################################
For standalone use set SYMBOL parameter at the bottom of this file
With margin terminal all under "if __name__ == "__main__":" it's not use

Set correct ID_EXCHANGE, see list of exchange in ms_cfg.toml

Check and set parameter at the TOP part of script

Verify init message in Strategy output window for no error
"""
################################################################
import toml
import sys
import executor as ex
from executor import *  # lgtm [py/polluting-import]
################################################################
# Exchange setup and parameter settings
################################################################
# Exchange setup
ex.ID_EXCHANGE = 7  # See ms_cfg.toml Use for collection of statistics *and get client connection*
ex.FEE_IN_PAIR = True  # Fee pays in pair
ex.FEE_MAKER = Decimal('0.075')  # standard exchange Fee for maker
ex.FEE_TAKER = Decimal('0.075')  # standard exchange Fee for taker
ex.FEE_SECOND = False  # On KRAKEN fee always in second coin
ex.FEE_BNB_IN_PAIR = False  # Binance fee in BNB and BNB is base asset
ex.GRID_MAX_COUNT = 5  # Maximum counts for placed grid orders
ex.EXTRA_CHECK_ORDER_STATE = False  # Additional check for filled order(s), for (OKEX, )
# Trade parameter
ex.START_ON_BUY = True  # First cycle direction
ex.AMOUNT_FIRST = Decimal('0.0')  # Deposit for Sale cycle in first currency
ex.USE_ALL_FIRST_FUND = False  # Use all available fund for first current
ex.AMOUNT_SECOND = Decimal('1000.0')  # Deposit for Buy cycle in second currency
ex.PRICE_SHIFT = 0.05  # 'No market' shift price in % from current bid/ask price
# Round pattern, set pattern 1.0123456789 or if not set used exchange settings
ex.ROUND_BASE = str()
ex.ROUND_QUOTE = str()
# x * PRICE_SHIFT also set max price drift from first grid order before shift grid orders
ex.PROFIT = Decimal('0.25')  # 0.15 - 0.85
ex.PROFIT_MAX = Decimal('0.85')  # If set it is maximum adapted cycle profit
ex.PROFIT_REVERSE = Decimal('0.5')  # 0.0 - 0.75, In Reverse cycle revenue portion of profit
ex.OVER_PRICE = Decimal('1.2')  # Overlap price in one direction
ex.ORDER_Q = 12  # Target grid orders quantity in moment
ex.MARTIN = Decimal('5')  # 5-20, % increments volume of orders in the grid
ex.SHIFT_GRID_DELAY = 15  # sec delay for shift grid action
# Other
ex.STATUS_DELAY = 60  # Minute between sending Tlg message about current status
ex.GRID_ONLY = False  # Only place grid orders for buy/sell asset
ex.LOG_LEVEL_NO_PRINT = []  # LogLevel.DEBUG Print for level over this list member
# Parameter for calculate grid over price and grid orders quantity in set_trade_condition()
# If ADAPTIVE_TRADE_CONDITION = True, ORDER_Q / OVER_PRICE determines the density of grid orders
ex.ADAPTIVE_TRADE_CONDITION = True
ex.BB_CANDLE_SIZE_IN_MINUTES = 60
ex.BB_NUMBER_OF_CANDLES = 20
ex.KBB = 2  # k for Bollinger Band
ex.PROFIT_K = 2 * 0.75 / ex.KBB  # k for place profit in relation to BB value
# Parameter for calculate price of grid orders by logarithmic scale
# If -1 function is disabled, can take a value from 0 to infinity (in practice no more 1000)
# When 0 - logarithmic scale, increase parameter the result is approaching linear
ex.LINEAR_GRID_K = 100  # See 'Model of logarithmic grid.ods' for detail
# Average Directional Index with +DI and -DI for Reverse conditions analise
ex.ADX_CANDLE_SIZE_IN_MINUTES = 1
ex.ADX_NUMBER_OF_CANDLES = 60
ex.ADX_PERIOD = 14
ex.ADX_THRESHOLD = 30  # ADX value that indicates a strong trend
ex.ADX_PRICE_THRESHOLD = 0.05  # % Max price drift before release Hold reverse cycle
# Start first as Reverse cycle, also set appropriate AMOUNT
ex.REVERSE = False
ex.REVERSE_TARGET_AMOUNT = 0.0
ex.REVERSE_INIT_AMOUNT = Decimal('0.0')
ex.REVERSE_STOP = False  # Stop after ending reverse cycle
##################################################################
ex.HEAD_VERSION = __version__
FILE_CONFIG = './ms_cfg.toml'
config = toml.load(FILE_CONFIG)
path = config.get('Path')
ex.LOG_PATH = path.get('log_path')
ex.WORK_PATH = path.get('work_path')
ex.LAST_STATE_PATH = path.get('last_state_path')
ex.EXCHANGE = config.get('exchange')
ex.VPS_NAME = config.get('Exporter').get('vps_name')
# Telegram parameters
telegram = config.get('Telegram')
ex.TELEGRAM_URL = config.get('telegram_url')
for tlg in telegram:
    if ex.ID_EXCHANGE in tlg.get('id_exchange'):
        ex.TOKEN = tlg.get('token')
        ex.CHANNEL_ID = tlg.get('channel_id')
        break


if __name__ == "__main__":
    if STANDALONE:
        # Set active pair
        SYMBOL = 'BTCUSDT'
        #
        import logging.handlers
        if len(sys.argv) > 1:
            # For autoload last state
            ex.LOAD_LAST_STATE = 1
        else:
            ex.LOAD_LAST_STATE = 0
        #
        FILE_LOG = f"{ex.LOG_PATH}mPw_{ex.ID_EXCHANGE}_{SYMBOL}.log"
        ex.FILE_LAST_STATE = f"{ex.LAST_STATE_PATH}{ex.ID_EXCHANGE}_{SYMBOL}.json"
        #
        logger = logging.getLogger('logger')
        logger.setLevel(logging.DEBUG)
        handler = logging.handlers.RotatingFileHandler(FILE_LOG, maxBytes=1000000, backupCount=10)
        handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        try:
            loop.create_task(main(SYMBOL))
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                loop.run_until_complete(ask_exit())
            except asyncio.CancelledError:
                pass
            except Exception as _err:
                print(f"Error: {_err}")
            loop.stop()
            loop.close()
