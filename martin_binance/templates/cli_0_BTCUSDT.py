#!/usr/bin/env python3
# -*- coding: utf-8 -*-
####################################################################
# Cyclic grid strategy based on martingale
# See README.md for detail
####################################################################
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.11"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"
"""
##################################################################
Disclaimer

All risks and possible losses associated with use of this strategy lie with you.
Strongly recommended that you test the strategy in the demo mode before using real bidding.
##################################################################
Check and set parameter at the TOP part of script
Verify init message in Strategy output window for no error
"""
################################################################
from decimal import Decimal
import sys
import asyncio
from pathlib import Path
import toml
import logging.handlers

from martin_binance import CONFIG_FILE, LOG_PATH, LAST_STATE_PATH
import martin_binance.params as ex
################################################################
# Exchange setup and parameter settings
################################################################
# Set trading pair for Strategy
ex.SYMBOL = 'BTCUSDT'
# Exchange setup, see list of exchange in ms_cfg.toml
ex.ID_EXCHANGE = 0  # See ms_cfg.toml Use for collection of statistics *and get client connection*
ex.FEE_MAKER = Decimal('0.1')  # standard exchange Fee for maker
ex.FEE_TAKER = Decimal('0.1')  # standard exchange Fee for taker
ex.FEE_FIRST = False  # For example fee in BNB and BNB in pair, and it is base asset
ex.FEE_SECOND = False  # For example fee in BNB and BNB in pair, and it is quote asset
# Setting for auto deposit BNB on subaccount for fee payment. For Binance subaccount only.
# See also https://github.com/DogsTailFarmer/martin-binance/wiki/How-it's-work#keeping-level-of-first-asset
ex.FEE_BNB = {
    'id_exchange': 0,                               # Where collected assets and keeping BNB volume
    'symbol': 'BNB/USDT',                           # Specified on the source strategy (id_exchange above)
    'email': 'sub-account@email.com',               # Email registered on this subaccount
    'target_amount': '0',                           # BNB in USD equivalent, no less than min_notional
    'tranche_volume': '0'                           # BNB in USD equivalent, no less than min_notional
}
ex.GRID_MAX_COUNT = 5  # Maximum counts for placed grid orders
# Trade parameter
ex.START_ON_BUY = True  # First cycle direction
ex.AMOUNT_FIRST = Decimal('0.05')  # Deposit for Sale cycle in first currency
ex.USE_ALL_FUND = False  # Use all available fund for initial cycle or alltime for GRID_ONLY
ex.AMOUNT_SECOND = Decimal('1000.0')  # Deposit for Buy cycle in second currency
ex.PRICE_SHIFT = Decimal('0.01')  # 'No market' shift price in % from current bid/ask price
# Search next parameter on Bybit https://www.bybit.com/en/announcement-info/spot-trading-rules/
ex.PRICE_LIMIT_RULES = Decimal('0')  # +-% from last ticker price. Use on Bybit only. 0 - disable
# Round pattern, set pattern 1.0123456789 or if not set used exchange settings
ex.ROUND_BASE = str()
ex.ROUND_QUOTE = str()
ex.PROFIT = Decimal('0.15')  # recommended FEE_MAKER*2<PROFIT<=0.85
ex.PROFIT_MAX = Decimal('0.85')  # If set it is maximum adapted cycle profit, PROFIT<PROFIT_MAX<=1.0
ex.OVER_PRICE = Decimal('0.6')  # Overlap price in one direction
ex.ORDER_Q = 12  # Target grid orders quantity in moment
ex.MARTIN = Decimal('10')  # 5-20, % increments volume of orders in the grid
ex.SHIFT_GRID_DELAY = 15  # sec delay for shift grid action
# Other
ex.STATUS_DELAY = 180  # Minute between sending Tlg message about current status, 0 - disable
ex.GRID_ONLY = False  # Only place grid orders for buy/sell asset
ex.LOG_LEVEL = logging.DEBUG  # Default level for console output
ex.COLLECT_ASSETS = False  # Transfer free asset to main account, valid for subaccount only
# Parameter for calculate grid over price and grid orders quantity in set_trade_condition()
# If ADAPTIVE_TRADE_CONDITION = True, ORDER_Q / OVER_PRICE determines the density of grid orders
ex.ADAPTIVE_TRADE_CONDITION = True
ex.BB_CANDLE_SIZE_IN_MINUTES = 60
ex.BB_NUMBER_OF_CANDLES = 20
ex.KBB = 2.0  # k for Bollinger Band
# Parameter for calculate price of grid orders by logarithmic scale
# If -1 function is disabled, can take a value from 0 to infinity (in practice no more 1000)
# When 0 - logarithmic scale, increase parameter the result is approaching linear
ex.LINEAR_GRID_K = 50  # See 'Model of logarithmic grid.ods' for detail
# Average Directional Index with +DI and -DI for Reverse conditions analise
ex.ADX_CANDLE_SIZE_IN_MINUTES = 1
ex.ADX_NUMBER_OF_CANDLES = 60
ex.ADX_PERIOD = 14
ex.ADX_THRESHOLD = 40  # ADX value that indicates a strong trend
ex.ADX_PRICE_THRESHOLD = 0.05  # % Max price drift before release Hold reverse cycle
# Start first as Reverse cycle, also set appropriate AMOUNT
ex.REVERSE = False
ex.REVERSE_TARGET_AMOUNT = Decimal('0')
ex.REVERSE_INIT_AMOUNT = Decimal('0')
ex.REVERSE_STOP = False  # Stop after ending reverse cycle
# Backtest mode parameters
ex.MODE = 'T'  # 'T' - Trade, 'TC' - Trade and Collect, 'S' - Simulate
ex.SAVE_DS = True  # Save session result data (ticker, orders) for compare
ex.SAVE_PERIOD = 4 * 60 * 60  # sec, timetable for save data portion
ex.SELF_OPTIMIZATION = True  # Cyclic self-optimization of parameters, together with MODE == 'TC'
ex.N_TRIALS = 250  # Number of optimization cycles for optuna study in self optimization mode
################################################################
#                 DO NOT EDIT UNDER THIS LINE                ###
################################################################
ex.PARAMS = Path(__file__).absolute()
ex.HEAD_VERSION = __version__
config = toml.load(str(CONFIG_FILE)) if CONFIG_FILE.exists() else None
ex.EXCHANGE = config.get('exchange')
ex.VPS_NAME = config.get('Exporter').get('vps_name')
# Telegram parameters
telegram = config.get('Telegram')
ex.TELEGRAM_URL = config.get('telegram_url')
for tlg in telegram:
    if ex.ID_EXCHANGE in tlg.get('id_exchange'):
        ex.TOKEN = tlg.get('token')
        ex.CHANNEL_ID = tlg.get('channel_id')
        ex.INLINE_BOT = tlg.get('inline')
        break


def trade(strategy=None):
    # For autoload last state
    ex.LOAD_LAST_STATE = 1 if len(sys.argv) > 1 else 0
    ex.LAST_STATE_FILE = Path(LAST_STATE_PATH, f"{ex.ID_EXCHANGE}_{ex.SYMBOL}.json")
    #
    if ex.MODE == 'S':
        _logger = logging.getLogger('logger_S')
    else:
        _logger = logging.getLogger('logger')
        log_file = Path(LOG_PATH, f"{ex.ID_EXCHANGE}_{ex.SYMBOL}.log")
        formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=1000000, backupCount=10)
        fh.setFormatter(formatter)
        _logger.addHandler(fh)
        _logger.setLevel(logging.DEBUG)  # Default level for files output

    logging.getLogger('hpack').setLevel(logging.INFO)
    _logger.propagate = False
    #
    if strategy is None:
        from martin_binance.executor import Strategy
        strategy = Strategy()
    loop = asyncio.get_event_loop()
    try:
        loop.create_task(strategy.main(ex.SYMBOL))
        loop.run_forever()
    except KeyboardInterrupt:
        pass  # user interrupt
    finally:
        try:
            loop.run_until_complete(strategy.ask_exit())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass  # user interrupt
        except Exception as _err:
            print(f"Error: {_err}")
        loop.run_until_complete(loop.shutdown_asyncgens())
    return strategy


if __name__ == "__main__":
    trade()
