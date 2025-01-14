"""
martin-binance strategy parameters
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2025 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.17"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import logging
from decimal import Decimal
from pathlib import Path

__all__ = [
    'SYMBOL', 'EXCHANGE', 'ID_EXCHANGE', 'FEE_MAKER', 'FEE_TAKER', 'FEE_FIRST', 'FEE_SECOND', 'FEE_BNB',
    'SAVE_ASSET', 'GRID_MAX_COUNT', 'START_ON_BUY', 'AMOUNT_FIRST', 'USE_ALL_FUND', 'AMOUNT_SECOND',
    'PRICE_SHIFT', 'PRICE_LIMIT_RULES', 'ROUND_BASE', 'ROUND_QUOTE', 'PROFIT', 'PROFIT_MAX', 'OVER_PRICE', 'ORDER_Q',
    'MARTIN', 'SHIFT_GRID_DELAY', 'GRID_UPDATE_INTERVAL', 'STATUS_DELAY', 'GRID_ONLY', 'LOG_LEVEL',
    'HOLD_TP_ORDER_TIMEOUT', 'COLLECT_ASSETS', 'GRID_ONLY_DELAY', 'ADAPTIVE_TRADE_CONDITION',
    'BB_CANDLE_SIZE_IN_MINUTES', 'BB_NUMBER_OF_CANDLES', 'KBB', 'LINEAR_GRID_K', 'ADX_CANDLE_SIZE_IN_MINUTES',
    'ADX_NUMBER_OF_CANDLES', 'ADX_PERIOD', 'ADX_THRESHOLD', 'ADX_PRICE_THRESHOLD', 'REVERSE', 'REVERSE_TARGET_AMOUNT',
    'REVERSE_INIT_AMOUNT', 'REVERSE_STOP', 'HEAD_VERSION', 'LOAD_LAST_STATE', 'LAST_STATE_FILE', 'VPS_NAME', 'PARAMS',
    'TELEGRAM_CONFIG', 'MODE', 'XTIME', 'SAVE_DS', 'SAVE_PERIOD', 'LOGGING', 'SELF_OPTIMIZATION', 'N_TRIALS',
    'SESSION_RESULT'
]

SYMBOL = str()
EXCHANGE = ()
# Exchange setup
ID_EXCHANGE = int()
FEE_MAKER = Decimal()
FEE_TAKER = Decimal()
FEE_FIRST = False
FEE_SECOND = False
FEE_BNB = {
    'id_exchange': 0,
    'symbol': 'BNB/USDT',
    'email': str(),
    'target_amount': '0',
    'tranche_volume': '0'
}
SAVE_ASSET = True
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
LOG_LEVEL = logging.DEBUG  # Default level for console output
HOLD_TP_ORDER_TIMEOUT = 30
COLLECT_ASSETS = bool()
GRID_ONLY_DELAY = 150  # sec delay before try restart GRID_ONLY cycle
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
TLG_SERVICE = False
TELEGRAM_CONFIG = {}
TLG_INLINE = False
# Backtesting
MODE = 'T'  # 'T' - Trade, 'TC' - Trade and Collect, 'S' - Simulate
XTIME = 1000  # Time accelerator
SAVE_DS = False  # Save session result data (ticker, orders) for compare
SAVE_PERIOD = 1 * 60 * 60  # sec, timetable for save data portion
LOGGING = True
SELF_OPTIMIZATION = True  # Cyclic self-optimization of parameters, together with MODE == 'TC'
N_TRIALS = 250  # Number of optimization cycles for optuna study
SESSION_RESULT = {}
