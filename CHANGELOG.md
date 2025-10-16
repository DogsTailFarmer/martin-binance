## 3.0.36 - 2025-10-16
🔧 fix(versions): update `exchanges-wrapper` to version `2.1.42` in `pyproject.toml` and `requirements.txt`  
📦 fix(dependencies): upgrade `ujson` to version `5.11.0` in `pyproject.toml` and `requirements.txt`  
📖 docs(changelog): update date for version `3.0.36` in `CHANGELOG.md`  
🔧 fix(strategy_base): adjust `reset_backtest_vars` logic for better initialization in `martin_binance/strategy_base.py`  
🔧 fix(executor): add `delta` to `initial_first` and `initial_second` in `martin_binance/executor.py`  
🔧 fix(client): update version to `3.0.36` in `martin_binance/client.py` 

### **Key Changes & Rationale**

#### 1. **Grid-Only Restart Logic Optimization**
   - **Change**:  
     - Added `self.grid_only_restart = 0` in the constructor of `Executor` in `executor.py` and in `collect_assets()`.  
     - Modified `event_grid_only_release()` to use `self.get_time() > self.grid_only_restart` for timing checks.  
     - Introduced `active_orders` condition in `grid_update()` to prevent unnecessary restarts.  
   - **Rationale**:  
     - Prevents premature or incorrect grid restarts by ensuring the restart delay (`GRID_ONLY_DELAY`) is respected.  
     - Ensures the grid is only restarted when all funds are used and no active orders exist, avoiding rapid or redundant cycles.  
     - Resets the restart timer to 0 after initiating a restart, preventing repeated triggers.  

#### 2. **Type Hinting Improvements**
   - **Change**:  
     - Replaced `()` with `tuple` in method return types (e.g., `get_free_assets()`, `calculate_profit_amounts()`).  
   - **Rationale**:  
     - Enhances code clarity and IDE support by explicitly stating that these methods return tuples of `Decimal` values.  
     - Aligns with Python 3.10+ type hinting standards (e.g., `tuple[Decimal, Decimal]`).  

#### 3. **API Update for Terminal Control**
   - **Change**:  
     - Replaced `window.attached_pane` with `window.active_pane` in `relaunch.py`.  
   - **Rationale**:  
     - Adapts to potential deprecations or changes in the terminal control library (e.g., `tmux` or `screen` bindings).  
     - Ensures commands are sent to the correct active terminal pane for session relaunch.  

#### 4. **Garbage Collection Monitoring**
   - **Change**:  
     - Added `gc.collect(generation=2)` logging in `collect_assets()`.  
   - **Rationale**:  
     - Monitors memory usage and garbage collection efficiency, aiding in performance debugging.  
     - Helps identify potential memory leaks or excessive object creation.  

#### 5. **Version & Copyright Updates**
   - **Change**:  
     - Updated `__version__` to `3.0.36b` and `3.0.36` in `__init__.py` and `relaunch.py`.  
     - Extended `__copyright__` year to `2021-2025`.  
   - **Rationale**:  
     - Standard practice for version control and legal compliance.  
     - Reflects ongoing maintenance and new features/fixes in the release.  

### **Impact on System Behavior**
1. **Stability**:  
   - Grid restarts now occur only after the required delay and under correct conditions, reducing the risk of infinite loops or redundant trades.  
2. **Maintainability**:  
   - Improved type hints and clearer method signatures make the codebase easier to navigate and extend.  
3. **Performance**:  
   - Garbage collection logging provides insights into memory management, enabling proactive optimization.  
4. **Compatibility**:  
   - Updated API calls ensure compatibility with newer versions of dependencies (e.g., terminal control libraries).  

## 3.0.35 - 2025-08-02
✨ feat(executor.py): update buy/sell order placement logic to use best_price
🛠️ fix(executor.py): adjust restore state message from "replace" to "create"
🛠️ fix(executor.py): add cancel_order_id and tp_hold reset on error handling

## 3.0.34 - 2025-07-02
🛠️ fix(client.py): remove redundant `else` in `register_client` method  
🛠️ fix(strategy_base.py): adjust indentation and structure in `fetch_order` method  
🛠️ fix(exchange_simulator.py): update return type and error handling in methods

## 3.0.33 - 2025-06-21
**Version Updates:**
   - The version number has been updated to `3.0.33` in all relevant files (`__init__.py`, `client.py`, `strategy.py`,
etc.).

**Error Handling:**
   - Removed redundant error handling for `asyncio.CancelledError`. This exception is generally not needed because it
indicates the task was cancelled, and further action is typically unnecessary.

**Asynchronous File Operations:**
   - Replaced synchronous file operations with asynchronous ones using `aiofiles` in several places to improve
performance:
     - Reading and writing JSON files.
     - Writing CSV files.

**Input Handling:**
   - Converted blocking input calls into non-blocking ones using `asyncio.to_thread` to prevent the event loop from
being blocked during user interaction.

**Exception Logging:**
   - Added more descriptive logging for exceptions, such as when failing to get a command from the Telegram proxy or
encountering other issues that might affect the operation of the bot.

**Code Refactoring:**
   - Improved code readability and maintainability by removing unnecessary comments and restructuring some sections of
the code.

**CSV Writing:**
   - Updated CSV writing logic to use `AsyncWriter` from `aiofiles` for asynchronous writing, ensuring that file
operations do not block the event loop.

## 3.0.32 - 2025-05-30
🔧 fix(executor): adjust conditions for currency deposits with GRID_ONLY logic

## 3.0.31 - 2025-05-27
🔧 fix(executor): correct handling of `delta` in conditional for `initial_first` and `initial_second` updates

## 3.0.30 - 2025-05-25
✨ feat(executor): refactor `grid_update` method and simplify TP order handling logic for clarity and efficiency.  
🔧 fix(executor): ensure grid orders placement when no open grid orders exist. 

## 3.0.29 - 2025-05-25
✨ refactor(lib.py): simplify `convert_from_minute` using intervals for improved readability and maintainability  
🔧 fix(executor.py): change type check to `isinstance` for `self.start_collect` in `event_exec_command`  
🔧 fix(executor.py): streamline condition checks in `on_new_ticker` for better clarity and performance

## 3.0.28 - 2025-05-12
🔧 chore(dependencies): update `exchanges-wrapper` to version 2.1.37 in `pyproject.toml` and `requirements.txt`  
🔧 fix(strategy): simplify `create_order_handler` method in `strategy_base.py`  

## 3.0.27 - 2025-04-25
🔧 chore(dependencies): bump `exchanges-wrapper` version to 2.1.36 in `pyproject.toml` and `requirements.txt`  
🔧 refactor(lib): update function return types to `dict` and `list` in `martin_binance/lib.py`  
🔧 refactor(strategy_base): update function return types to `list` in `martin_binance/strategy_base.py`  

## 3.0.26 - 2025-04-24
🔒 fix(tlg_client, tlg_proxy): set minimum SSL/TLS version to 1.2 for enhanced security  
🔧 chore(init): bump version to 3.0.26 in `__init__.py`  

## 3.0.25 - 2025-04-24
🔧 fix(pyproject.toml, requirements.txt): update `exchanges-wrapper` version to 2.1.35 for compatibility  
📝 docs(README.md): update configuration instructions for `exchanges-wrapper` to version 3.0.25  
🔄 chore(README.md): change `HUOBI` to `HTX` and `OKEX` to `OKX` in referral links  

### Update
✨ [UPDATE](pyproject.toml/CHANGELOG.md): Bump dependencies and version.

## 3.0.23 - 2025-03-10
### Fix
* `restore_strategy_state`: Logical error when processing orders that were sent before shutdown and no response
was received
* `on_balance_update_ex`: doubling the adjustment of the initial balance with a positive replenishment in the opposite
coin

### Update
* Added `trade_id` to debug output
* Bump requirements
* `grafana.json` template
* Some minor improvements

## 3.0.22 - 2025-02-20
### Update
* Bump requirements

## 3.0.21 - 2025-02-07
### Update
* Some minor improvements

## 3.0.20 - 2025-02-06
### Update
* `Bybit`: checking for the minimum/maximum Buy/Sell orders price is [excluded](https://announcements.bybit.com/article/title-adjustments-to-bybit-s-spot-trading-limit-order-mechanism-blt786c0c5abf865983/)
* Bump requirements
* Some minor improvements

## 3.0.19 - 2025-01-27
### Fix
* `on_balance_update_ex`: calculating initial balance for opposite coin in Reverse cycle

### Update
* `funds_rate_exporter.py`: optimized current price queries on `coinmarketcap`
* Functions for placing and canceling orders have been optimized
* Bump requirements

## 3.0.18 - 2025-01-18
### Update
* Change dependency model for exchanges-wrapper
* Up requirements for exchanges-wrapper>=2.1.26

## 3.0.17 - 2025-01-16
### Fix
* Restored reverse_price value if it is omitted
* `GRID_ONLY` mode: incorrect check of minimum trading volume
* Erroneous correction of the opposite coin when withdrawing in a reverse cycle is excluded
* Restarting a session in case of network failures when sharing a client between pairs
* Interaction with the Telegram service, consolidation of messages and distribution of commands through
a centralized proxy service, default use tlg_proxy service disabled

### Added new features
* `funds_rate_exporter.py`: add export data to IPv6 interface

### Update
* Bump requirements
* Moving control and updating MAX_QUEUE_SIZE for on_*_update loops to server side

## 3.0.16 - 2024-11-01
### Fix
* Unnecessary restart when updating assets
* Add parameter `SAVE_ASSET`, to selectively suppress this [feature](https://github.com/DogsTailFarmer/martin-binance/wiki/How-it's-work#save-data-for-external-analytics)

## 3.0.15 - 2024-09-14
### Update
* Up requirements for exchanges-wrapper==2.1.20
* Add `betterproto` to requirements

## 3.0.14 - 2024-09-13
### Fix
* `pyproject.toml`

## 3.0.13post1 - 2024-09-13
### Fix
* deepsource found style issue

## 3.0.13 - 2024-09-13
### Fix
*  Sometimes get error from backtesting on Exit [#81](https://github.com/DogsTailFarmer/martin-binance/issues/81#issue-2465248437) 

### Added new features
* (3.0.13b4) Handling missed asset update events of GRID_ONLY and USE_ALL_FUND modes

### Update
* Up requirements for exchanges-wrapper==2.1.18
* Dependency
* Some minor improvement

## 3.0.12 - 2024-08-13
### Fix
* Calculating`self.reverse_price` before immediately starting Reverse cycle also. It can be used later in
`on_balance_update_ex`
* `on_balance_update_ex`: initial balance update logic
 
## 3.0.11 - 2024-07-13
### Added new features
* [Maintaining a supply of BNB in sub-account to pay fees](https://github.com/DogsTailFarmer/martin-binance/wiki/How-it's-work#maintaining-a-supply-of-bnb-in-a-sub-account-to-pay-fees)

## 3.0.10 - 2024-07-07
### Fix
* `on_balance_update_ex`: excessive recalculation of income when withdrawing funds

### Update
* Processing account replenishment in all states with increasing turnover
* Dependency

## 3.0.9 - 2024-07-07
### Added new features
* Updated `APY profit rating` Grafana report, used data from selected time range for APY calculation
* Processing [account replenishment](https://github.com/DogsTailFarmer/martin-binance/wiki/How-it's-work#deposit-and-withdraw-assets-on-active-strategy) in all states with increasing turnover

## 3.0.8 - 2024-06-26
### Fix
* Version compatibility

### Added new features
* Continue interrupted grid update cycle after restart

### Update
* Dependency

## 3.0.7 - 2024-05-02
### Fix
* `Docker`: server-client deployment functionality restored (`exchanges-wrapper` and `martin-binance`), also for Windows

### Update
* `RATE_LIMITER` initial settings changed
* Up requirements for exchanges-wrapper==2.1.12

## 3.0.6 - 2024-04-19
### Fix
* Unattended cancelling keepalive tasks

### Added new features
* The total income includes withdrawn funds

### Update
* Up requirements for exchanges-wrapper==2.1.11
* Refine handling backtest process 

## 3.0.5 - 2024-04-16
### Update
* Up requirements for exchanges-wrapper==2.1.10
* Import from `params` module
* Some issues `Mismatch between signature and use of an overridden method`

## 3.0.4 - 2024-04-14
### Fix
* Creating and manage asynchronous tasks

### Update
* Up requirements for exchanges-wrapper==2.1.9
* 'Backtesting': some minor improvements
* Remove cross-version updates

## 3.0.3 - 2024-04-08
### Update
* Refine templates handling
* `Backtesting`: extract trial parameters into `/home/ubuntu/.MartinBinance/trial_params.json`, [detail here.](https://github.com/DogsTailFarmer/martin-binance/wiki/Back-testing-and-parameters-optimization#some-details)
* `Backtesting`: add logging importance parameters rating for each optimisation cycle
* Up requirements for exchanges-wrapper==2.1.8

## 3.0.2 - 2024-04-03
### Fix
* `Backtesting`: updating the balances at slippage
* `class PrivateTrade:` convert trade_id to int()
* `Backtest control`: orjson.JSONDecodeError: unexpected character: line 1 column 1 (char 0)

### Update
* Up requirements for exchanges-wrapper==2.1.7
* Some minor improvement

## 3.0.1 - 2024-03-31
### Refined and added new features
* Project architecture
* :rocket: Cyclic Backtesting workflow with update base trade parameters
* :rocket: `Backtesting`: handling of partially filling events
* :rocket: Migrate `gRPC` from [grpcio](https://grpc.io/) to [grpclib](https://github.com/vmagamedov/grpclib) + [python-betterproto](https://github.com/danielgtaylor/python-betterproto)
* Logging improvement
* `Analytics`: Refine unload and processing assets data
* Refactoring processing periodically events based on [schedule](https://github.com/dbader/schedule)
* New strategy mode: [Keeping level of first asset](https://github.com/DogsTailFarmer/martin-binance/wiki/How-it's-work#keeping-level-of-first-asset)

### Update
* Up requirements for exchanges-wrapper==2.1.6

## 3.0.1rc7 - 2024-03-26
### Update
* Refactoring processing periodically events
* Up requirements for exchanges-wrapper==2.1.5

## 3.0.1rc3 - 2024-03-21
### Added for new features
:rocket: `Backtesting`: handling of partially filling events

### Update
* Up requirements for exchanges-wrapper==2.1.3

## 3.0.1rc1 - 2024-03-19
### Fix
* Cyclic Backtesting workflow

### Update
* Up requirements for exchanges-wrapper==2.1.2


## 3.0.0rc22 - 2024-03-13
### Fix
* `Analytics`: Refine unload and processing assets data

### Update
* Up requirements for exchanges-wrapper==2.1.0

## 3.0.0rc20 - 2024-03-12
### Fix
* `cancel_order_call()`: incorrect using asyncio.wait_for()

### Update
* logging improvement
* fee settings and handling

## 3.0.0rc19 - 2024-03-11
### Update
* Replaced checking price when calculating TP vs updating price based on order book if error occurred
* Don't unload assets on *`test`* accounts for avoid overload limited `coinmarketcap` API
* Startup sequence optimization
* Up requirements for exchanges-wrapper==2.0.1

## 3.0.0rc18 - 2024-03-10
### Update
* Added price check when calculating TP in relation to the average filling price of the last grid order.
 Relevant for extreme volatility, was noticed on the test network.

## 3.0.0rc17 - 2024-03-10
### Update
* Refine grid orders control

### Added for new features
* `Backtesting`: save session collected date to `session_root/raw_bak.zip`

## 3.0.0rc14 - 2024-03-09
### Update
* Up requirements for exchanges-wrapper==2.0.0
* Refined logging

## 3.0.0rc8 - 2024-03-08
### Fix
* logging for Simulate mode

### Update
* :rocket: Migrate `gRPC` from [grpcio](https://grpc.io/) to [grpclib](https://github.com/vmagamedov/grpclib) + [python-betterproto](https://github.com/danielgtaylor/python-betterproto)
* Binance: handling `EXPIRED_IN_MATCH`
* `WSS`: check and restart

## 3.0.0rc1 - 2024-03-02
* `on_balance_update_ex()`: don't update direct initial asset values in Reverse cycle
* Partially filled TP in Hold reverse cycle

### Update
* Project architecture

## 2.1.5 - 2024-02-25
### Fix
* ModuleNotFoundError: No module named 'optimizer' #73

### Update
* Do not send orders if it was getting 'FAILED_PRECONDITION' response
* Do not start Telegram control process for Simulate mode or if bot id is not setting
* Do not start DB control process for Simulate mode
* Changed initialization sequence during recovery from saved state

## 2.1.4 - 2024-02-22
### Fix
* `on_new_funds()`

### Update
* Refine initialization backtesting
* Up requirements for exchanges-wrapper==1.4.15

## 2.1.3 - 2024-02-20
### Fix
* `calc_profit_order()`: rounding for `target_amount_first`
* `restore_strategy_state()`: Tlg control thread

### Update
* Some minor updates
* Up requirements for exchanges-wrapper==1.4.14
* Running `*_utils.py` modules as daemon

## 2.1.2 - 2024-02-17
### Fix
* Create limit order error handler
* Start simulate mode from saved state

## 2.1.1 - 2024-02-16
### Fix
* `check_min_amount()`
* `restore_strategy_state()`
* Fix issue with csv empty lines on windows (#71)

## 2.1.0 - 2024-02-16
### Added for new features
:rocket: Complete cyclic optimization of strategy parameters based on [`optuna` framework](https://optuna.readthedocs.io/en/stable/index.html)
For reference see [Parameters optimization](https://github.com/DogsTailFarmer/martin-binance/wiki/Back-testing-and-parameters-optimization#parameters-optimization)

### Update
* `cancel_order_call`: added timeout handler
* Utilised partially filled TP amount during grid update
* `create_limit_order`: Supress call strategy handler for `grpc.StatusCode.FAILED_PRECONDITION` exception,
fire tlg message only. As a result, there are no attempts to re-place the order with incorrect condition.

## 2.1.0rc36 - 2024-02-11
### Fix
* `on_order_update_handler`: refine

### Update
* Up requirements for exchanges-wrapper==1.4.12

## 2.1.0rc33 - 2024-02-11
### Update
* Some minor updates

## 2.1.0rc32 - 2024-02-11
### Fix
* Event updates arrived before the saved state was restored

## 2.1.0rc31 - 2024-02-11
### Fix
* `check_min_amount()`: `self.tp_amount`

### Update
* Up requirements for exchanges-wrapper==1.4.11

## 2.1.0rc29 - 2024-02-09
### Update
* `check_min_amount()`: refine check min trade amount for SELL cycle
* Up requirements for exchanges-wrapper==1.4.10

## 2.1.0rc28 - 2024-02-07
### Update
* Up requirements for exchanges-wrapper==1.4.9

## 2.1.0rc27 - 2024-02-07
### Update
* 'relaunch.py': improved
* Up requirements for exchanges-wrapper==1.4.9b5 (test grpc 1.60.1)

## 2.1.0rc25 - 2024-02-02
### Update
* Up requirements for exchanges-wrapper==1.4.8

## 2.1.0rc20 - 2024-01-27
### Fix
* An order that was `PARTIALLY FILLED` at the time of creation was counted as `FILLED`

### Update
* margin_wrapper.buffered_funds(): some minor improvements
* executor.get_free_assets(): for "free" mode the volume of the utilized deposit is taken into account when not TP
* rollback saving/restore trades history, but used for it specified file in `/last_state/X_AAABBB.csv`
* executor: remove parameters `SAVE_TRADE_HISTORY` and `SAVED_STATE`, already use for saving/restore trade events
* comprehensive improvement of the internal accounting and recovery system
* Up requirements for exchanges-wrapper==1.4.7
* Dependency: Up requirements for Python>=3.9

### Added for new features
* Per 10 mins update trade rules for pair
* If new trade rules prevent the grid from placing orders, then the grid will be forced to be re-set
* Add parameter`SELF_OPTIMIZATION = True`  # Cyclic self-optimization of parameters, together with `MODE == 'TC'`

## 2.1.0rc1 - 2024-01-05
### Update
* `SAVE_TRADE_HISTORY = False` set default
* calculation `over price` for Reverse cycle : checking result on true positive, correction it if needed
* [For backtesting change format saved data from Pickle to Feather #64](https://github.com/DogsTailFarmer/martin-binance/issues/64#issue-1858138993)
    + Change format to [Apache Parquet](https://parquet.apache.org)
    + Restrictions on the size of RAM have been removed due to write/read buffering
    + Use orjson for de/serialize stream data
* replacing `json` with `ujson` to improve performance

## 2.0.7 - 2023-12-13
### Update
* Up requirements for exchanges-wrapper==1.4.4

## 2.0.6 - 2023-12-12
### Update
* Up requirements for exchanges-wrapper==1.4.3 [fixed #42](https://github.com/DogsTailFarmer/exchanges-wrapper/issues/42)

## 2.0.5 - 2023-12-11
### Update
* Refining restoration of grid orders after their execution during the grid shift process
* Up requirements for exchanges-wrapper==1.4.2
* Some minor changes

## 2.0.4 - 2023-12-08
### Update
* `funds_rate_exporter.py`: average CPU load present as percent value at 1 minute period
* `solve()`, `calc_grid()`: use [scipy.optimize.minimize](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize.html#scipy-optimize-minimize)
for calculation Reverse cycle over price
* optimize CPU loads at last_state_update()
* convert_tp(): clear start_hold state and initialize restore grid orders
* Up requirements for exchanges-wrapper==1.4.1

## 2.0.3 - 2023-12-01
### Fix
* Backtesting, Simulation mode

### Update
* solve(): The limit of attempts has been increased
* calc_over_price(): The range of changes in the number of orders has been expanded

## 2.0.2 - 2023-11-26
### Fix
* Version tags

## 2.0.1 - 2023-11-26
### Fix
* "Groggy" state after start canceling grid before update it

### Update
* Improved calc_over_price()

## 2.0.0.post2 - 2023-11-24
### Fix
*  Exception buffered_orders: 'NoneType' object is not subscriptable #68

## 2.0.0.post1 - 2023-11-23
### Fix
* Fix issue detected by SonarCloud

## 2.0.0 - 2023-11-23
### Fix
*  Order price must be higher than the minimum price #67

### Update
* Up requirements for exchanges-wrapper==1.4.0
* Some minor improvements

## 2.0.0rc8 - 2023-11-16
### Fix
* Handling of partially filled TP when Reverse hold
* Part filled TP and part filled grid orders, unnecessary adjustment sum_amount_

### Update
* Refine cli_X_AAABBB.py
* Remove db support to module
* Remove Telegram support to module
* README.md updated
* Clear from margin code fragments compatibility
* decimal.Decimal calculation for all modules was implemented
* Up requirements for exchanges-wrapper==1.4.0rc6

## 2.0.0rc1 - 2023-11-01
### Added for new features
* Bybit exchange V5 API support implemented. Supported account type is
 [Unified Trading Account](https://testnet.bybit.com/en/help-center/article/Introduction-to-Bybit-Unified-Trading-Account),
 for main and sub-accounts. Spot Trading only.

### Update
* Lost compatibility with margin.de terminal. Scripts developed for use with the terminal can be run as
executable modules, but not the other way around.
* The logic and implementation of monitoring exceptional situations when placing and deleting orders has been updated.
* Improved gRPC outage exception handling
* Up requirements

## 1.3.7.post3 - 2023-10-09
### Fix
* calc_profit_order(): rounding issue when correction tp amount on step_size

### Update
* Up requirements for exchanges-wrapper==1.3.7.post4

## 1.3.7.post2 - 2023-10-05
### Fix
* Fix: Refine exception handling when deleting a grid of orders, one of which is partially filled

### Update
* Up requirements for exchanges-wrapper==1.3.7.post3

## 1.3.7.post1 - 2023-09-30
### Fix
* Sonarcloud issues

## 1.3.7 - 2023-09-30
### Update
* Up requirements for exchanges-wrapper==1.3.7.post2

## 1.3.7b1 2023-09-26
### Added for new features
* Save trading (filling orders) and transfer asset history into a file `~/.MartinBinance/log/X_AAABBB.csv`
  
headers:
```
"TRADE","transaction_time","side","order_id","client_order_id","trade_id","order_quantity","order_price","cumulative_filled_quantity","quote_asset_transacted","last_executed
"TRANSFER","event_time","asset","balance_delta"
```
data:
```
"TRADE","1695745010026","SELL","9850221","4815001","1716764","0.00539700","26193.86000000","0.00539700","141.36826242","0.00539700","26193.86000000" 
"TRANSFER","1695745010027","LTC","-0.001"
```

## 1.3.6.post1 2023-09-25
### Update
* Limit for grid updates, updated when:
  + For Original cycle: the amount of free deposit not involved in the turnover more than 35%
  + For Reverse cycle: the amount of free deposit not involved in the turnover more than 65%

## 1.3.6 2023-09-24
### Fix
* Due to a rounding error, the order status was incorrectly fetched if it was partially completed

### Update
* Up requirements for exchanges-wrapper==1.3.7.post1

### Added for new features
* To boost trade in case of low market volatility: TP order is updated once every 15 minutes,
    and in Reverse cycle grid update once an hour

## 1.3.5-1.dev1
* Fix: Error getting internal id while re-placing grid order

## 1.3.5-1.dev0
* Update: On-the-fly update assets with withdrawal and deposit operations also for Reverse cycle

## 1.3.5 2023-09-19
### Fix
* Fix: Incorrect calculated depo volume for grid update, not include held grid orders volume
* Up requirements for exchanges-wrapper to 1.3.7

### Update
* Restored MS_ORDERS, convert from list to dict (inter-version compatibility), clear

## 1.3.4rc5-1 2023-08-24
### Update
* `relaunch.py`: update deprecation method for `libtmux==0.22.1` 

### Fix
* [ Windows path can't contain ':' symbol #65 ](https://github.com/DogsTailFarmer/martin-binance/issues/65)

## 1.3.4rc5 2023-08-20
### Fix
* Up requirements for exchanges-wrapper to 1.3.6b7

## 1.3.4rc4-5 2023-08-19
### Fix
* Up requirements for exchanges-wrapper to 1.3.6b6
* Up other requirements
* Some minor improvements

## 1.3.4rc4-4
### Fix
* [Handling additional TP filled by market after placed additional grid after filled grid after filled ordinary TP](https://github.com/DogsTailFarmer/martin-binance/issues/62#issue-1856466446)

## v1.3.4rc2 2023-08-10
### Info
* Starting with version `martin-binance 1.3.4`, compatibility with `margin` will be lost, since some new parts
of the code are no longer supported by implemented `Python 3.7`. I'm focused on `Python 3.10`.
I won't rid the code of numerous compatibility elements yet, so if the margin team will update its version,
everything should work.

## v1.3.4rc1 2023-08-09
### Fix
* Processing of the situation when at bulk cancel of the grid orders and one or more of orders are FILLED.
  - cancel loop is interrupted
  - orders with received CANCELED status are restored
  - status is requested for unconfirmed orders and processing is performed: recovery if status is CANCELED,
  - normal processing in case of filling in

* Processing of the situation when after partially filled TP one or some or all grids are filled

* `executor.get_free_assets(mode='free')`: incorrect balance for opposite asset (always 0),
as a result - a negative value of free funds
* `margin_wrapper.restore_state_before_backtesting()`: tmp upgrade issue - convert cls.orders to dict

### Added for new features
* `OoTSP.py`: add interactive option *Get parameters for specific trial*

### Update
* Backtesting: 100% repeatability of test and initial sessions at the same parameters is achieved.
Ticker history includes fulfillment events that may not be in the original stream. I.e. the order was executed
at price P, and there was no such price in the stream at a given time period. This led to a divergence of the test
session against the original (reference).

<!--suppress ALL -->

<img height="350" src="https://user-images.githubusercontent.com/77513676/253804148-ed92bf13-ca04-46bf-8714-28380d0c2e52.png" width="350"/>

* `README.md`: some design correction
* Remove parameter `ex.EXTRA_CHECK_ORDER_STATE` and the corresponding function
* Up requirements for grpcio to 1.56.0
* Up requirements for exchanges-wrapper to 1.3.4

## v1.3.3 2023-07-04
### Added for new features
* Send alarm (to db) if exist unreleased grid orders or hold TP
* Up requirements for exchanges-wrapper to 1.3.3

## v1.3.2-3 2023-07-02
### Fix
* fetch_order(): fixed status for archived order (remove it from StrategyBase.orders)

### Update
* get_free_assets() added 'available' mode for initial funds check

## v1.3.2-2 2023-07-01
### Fix
* Incorrect internal accounting of active orders
* Changed StrategyBase.orders from list to dict
* Some improvements in save/restore

## v1.3.2 2023-06-29
### Fix
* buffered_orders() was try fetch orders and generate event on stopped strategy, full refactoring restore
from saved state

### Update
* remove all_trades and all_orders class variables from StrategyBase as redundant
* Up requirements for exchanges-wrapper to 1.3.2

## v1.3.1-2 2023-06-28
### Update
* funds_rate_exporter: optimized response rate to free balance change
* client session id changed from uuid to shortuuid

### Added for new features
* optuna: add visualization contour_plot and slice_plot

## v1.3.1-1 2023-06-22
### Fix
* BACKTEST "S" mode: Restore an TP from a saved state, was missing

### Added for new features
* BACKTEST "S" mode: add progress bar
* BACKTEST "S" mode: supress logging

## v1.3.1 2023-06-21
### Update
* Up requirements for exchanges-wrapper to 1.3.1
* Refactoring the deployment process

## v1.3.0-4 2023-06-20
### Fix
* ```get_free_assets(mode='free', backtest=True)``` return incorrect value for backtest Reverse cycle 

### Update
* Sometimes Tmux terminal after reboot not restore work path to ```/exch_srv.py```
For working case: in relaunch.py was changed './exch_srv.py' to 'exch_srv.py' and
path ```~/.local/lib/python3.10/site-packages/exchanges_wrapper``` must be added to system PATH

For Ubuntu at end of ```~/.bashrc``` add the string

```
export PATH=$PATH:~/.local/lib/python3.10/site-packages/exchanges_wrapper
```
and refresh bash ```source ~/.bashrc```

## v1.3.0-3 2023-06-10
### Fix
* Change ast.literal_eval() to eval() for trusted source

## v1.3.0-2 2023-06-19
### Added for new features
* Ability to start backtesting from saved state, including in Reverse mode

### Update
* Monitoring memory usage including swap
* up requirements for exchanges-wrapper to 1.3.0-2

## v1.3.0-1 2023-06-10
### Fix
* Some minor improvements

## v1.3.0 2023-06-09
### Added for new features
* Backtesting capabilities
* Based on [optuna framework](https://optuna.org) search for optimal trading parameters
* Visual comparison of the results of the initial and trial trading sessions

### Update
* Doc migrate from readme to wiki 

## v1.3.0b22-23 2023-06-08
### Fix
* correct funding check in start()

## v1.3.0b18-21 2023-06-06
### Fix
* #59

### Update
* Sync record/play
* Add SAVE_DS = True  # Save session result snapshot (ticker, orders) for compare
* up requirements for exchanges-wrapper to 1.3.0-1
* refactoring class StrategyBase
* + backtest_data_control()
 
## v1.3.0b12 2023-06-02
### Fix
* deepsource issues

## v1.3.0b11 2023-06-01
### Fix
* Bitfinex: rename test pair from AAABBB to TESTBTCTESTUSDT, update template

### Update
* protobuf format for CreateLimitOrder() method. **Not compatible with earlier versions**
* for some situation (shift grid, cancel grid after filled TP and so on) changed cancel order method from "one by one"
to bulk mode

## v1.2.18-8 2023-06-xx not released
### Fix
* collect_assets() incorrect convert small decimal.Decimal values to str

### Update
* For STANDALONE mode refactoring call environment for place_limit_order(), avoid unnecessary Decimal -> float
conversions
* Add error handling for atr()
* Some minor improvements

## v1.2.18-4 2023-05-18
### Added for new features
* Use ATR (Average True Range with 14 period x 15 min) indicator when
[calculate first grid order volume](https://github.com/DogsTailFarmer/martin-binance/discussions/57#discussion-5167551)

### Update
* Grafana template: Consolidated asset valuation - Assets by place: group by exchange name instead of account name
* Halved the amount of buffer data to save memory (KLINES_LIM, ALL_TRADES_LIST_LIMIT, TRADES_LIST_LIMIT)

## v1.2.18-1 - 2023-05-07
### Fix
* [#58](https://github.com/DogsTailFarmer/martin-binance/issues/58#issue-1698914151)
  A failed optimization of martin_binance/margin_wrapper.buffered_orders() was in version 1.2.16


## v1.2.18 - 2023-05-06
### Fix
* Correct ending GRID ONLY cycle if USE_ALL_FUND = False 

### Update
* Refactoring set_profit() for precision calculate TP order price
* Parameter PROFIT_K excluded
* README.md

## v1.2.16-1-HotFix - 2023-04-12
### Fix
* Binance: REST API update for endpoint: GET /api/v3/exchangeInfo was changed MIN_NOTIONAL filter

### Update
* up requirements for exchanges-wrapper to 1.2.10-6

## v1.2.16 2023-04-05
### Fixed
* Handling missed order event after restore from current state
* Exception [<class 'decimal.DivisionByZero'>] if PROFIT_MAX is not setting
* Some minor improvements

### Update
* up requirements for exchanges-wrapper to 1.2.10-5

## v1.2.15-2 2023-03-31
### Fixed
* Bitfinex: was changed balance update order #56 

## v1.2.15-1 2023-03-13
### Added for new features
* Refactoring and updated auto-convert possibilities [Grid only mode](https://github.com/DogsTailFarmer/martin-binance#grid-only)

### Update
* up requirements for exchanges-wrapper to 1.2.10-4

## v1.2.14-1 2023-02-24
### Added for new features
* Periodically checking WSS status for active trade by client side.
This correctly stops the server-side service in the event of an abnormal client shutdown
and guarantees the service for an active trading session.

## v1.2.14 2023-02-22
### Fixed
* Fixed #53

### Added for new features
* Transfer free assets to main account, resolve #54

## v1.2.13-6 2023-02-04
### Fixed
* [PR#47](https://github.com/DogsTailFarmer/martin-binance/pull/47#issue-1561537039)
* [Fix shebang](https://github.com/DogsTailFarmer/martin-binance/issues/48#issue-1561939620)

### Update
* Some minor improvements
* up requirements for exchanges-wrapper to 1.2.9-2

## v1.2.13-5 2023-01-23
### Added for new features
* Restart option for Telegram remote control from last saved state

### Update
* Some minor improvements
* up requirements for exchanges-wrapper to 1.2.9-1

## v1.2.13-3 2023-01-11
### Fixed
* Optimized numerical solution of grid parameters in Reverse cycle to avoid rare cases of calculation failure
  + search for a solution with the specified or maximum possible accuracy
  + effectively finding possible accuracy, as a result, reducing the number of iterations by about 4 times
  + forced displacement of the starting point during looping allows to find a solution with possible accuracy,
  if it exists under given conditions

### Update
* Config templates
* Removing FTX smell
* Add cumulative Free assets chart into Grafana template
* up requirements for exchanges-wrapper to 1.2.9

## v1.2.12 2023-01-01
### Added for new features
* Add connection to Binance US (binance.us)

### Update
* up requirements for exchanges-wrapper to 1.2.8

## v1.2.11 2022-12-20
### Fixed
* fix #43, import error in margin mode under Windows

## v1.2.10-8 2022-12-15
### Fixed
* fix #42
 
### Update
* up requirements for exchanges-wrapper to 1.2.7-7

## v1.2.10-7 2022-12-14
### Fixed
* fix #39, fix #40, fix #41
* grid_handler: No grid orders after part filled TP, fixed additional order params
and part code refactoring

## v1.2.10-6 2022-12-08
### Update
* up requirements for exchanges-wrapper to 1.2.7-6
* Some minor improvements

## v1.2.10-5 2022-12-04
### Update
* OKX: adding delay in place_limit_order() for avoid exceeding the rate limit (60 orders / 2s)
* Some minor improvements
* up requirements for exchanges-wrapper to 1.2.7-5

## v1.2.10-4 2022-11-25
### Update
* up requirements for exchanges-wrapper to 1.2.7-4

## v1.2.10-3 2022-11-25
### Fixed
* saving the state for partially executed orders as float() instead of Decimal() causes an error when restarting
from the saved state if the last snapshot contains partial execution data.

## v1.2.10-2 2022-11-25
### Fixed
* save/restore internal order_id

## v1.2.10-1 2022-11-24
### Update
* up requirements for exchanges-wrapper to 1.2.7-3

## v1.2.10 2022-11-23
### Update
* internal numbering for orders
* Processing of partial order execution events is linked to a specific order number.
Previously, events were processed sequentially, which led to an error when the order of receiving events was violated.

## v1.2.9-18 2022-11-21
### Update
* Dependency to exchanges-wrapper 1.2.7-1

## v1.2.9-18 2022-11-21
### Fixed
* #36
* #37

## v1.2.9-14 2022-11-11
### Fixed
* After restart from saved state incorrect value for first_run may cause incorrect data to be saved
for the start deposit. Because of this, the control of initial balances may not work correctly.
* Calculate parameters for grid. Adding price limitation based on [PERCENT_PRICE](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md#percent_price)
filter. Without such limit, the task of finding grid parameters for a given volume has several solutions, including in
the area of negative price values. This is an unlikely event that could have been within the Reverse buy cycle and
high volatility

### Update
* Changed logic for place order error handling. Before - save to hold uncompleted order and wait event from exchange.
Now - resend order after timeout.
* Refactoring place_grid() and calc_grid()

### Added for new features
* Before start of cycle and in periodically report are showed free assets' data, what volume of coins does
not participate in the turnover

> 19/10 22:26:23 Start
> 
>Start process for .db save
> 
>Start process for Telegram
> 
>Number of unreachable objects collected by GC: 16
> 
>19/10 22:26:23 Initial first: 1.009025, second: 9829.04880062
> 
>**19/10 22:26:23 Free: First: 1.009025, second: 9629.04880062**
> 
>19/10 22:26:24 Start Buy cycle with 200.0 USDT depo

* #7 Allow to withdraw and deposit on active strategy with autocorrection initial balance and depo. See
[manual](https://github.com/DogsTailFarmer/martin-binance#deposit-and-withdraw-assets-on-active-strategy) for detail

## v1.2.9-1 2022-10-14
### Update
* Refusal to use PROFIT_REVERSE parameter.
Valid for Reverse cycle. For a small deposit, the cycle income can be equal to the minimum order size step.
If you divide it into parts to increase the deposit and make a profit, as a result of rounding the deposit amount does
not increase, which negatively affects the ability of the strategy to complete the reverse cycle.
Instead, all cycle profits are allocated either to increase the deposit (for an odd cycle number)
or to accumulate profits (for an even cycle number)

## v1.2.9 2022-10-13
### Added for new features
* Huobi exchange implemented

### Update
* Dependency exchanges-wrapper==1.2.6

## v1.2.8-2 2022-09-29
### Fixed
* For analytic export replace Bitfinex mapping from "IOTA to MIOTA" to "IOT to MIOTA"
* Migration transition solution cleared for saved_state from 1.2.6 - > 1.2.7
* lgtm [py/unused-import]

### Update
* get_min_buy_amount()

## v1.2.8-1 2022-09-27
### Fixed
* For analytic export replace IOTA to MIOTA for Bitfinex

### Update
* dependency exchanges-wrapper up to 1.2.5-3 

## v1.2.8 2022-09-26
### Added for new features
* Powered by [Docker](https://www.docker.com/) deploy

## v1.2.7-1 2022-09-25
### Fixed
* #26 #29 - add preliminary calculation of grid parameters
```console
25/09 16:33:07 set_trade_conditions: buy_side: False, depo: 0.050000, base_price: 18950.35, reverse_target_amount: 0, amount_min: 0.000528, step_size: 0.000001, delta_min: 0.01
25/09 16:33:07 set_trade_conditions: depo: 0.050000, order_q: 48, amount_first_grid: 0.000528, amount_2: 0.0005808, q_max: 24, coarse overprice: 1.210355
25/09 16:33:07 For Sell cycle will be set 24 orders for 1.2104% over price
```
Before start, you can correct value depo and other trade parameters 

* #30 Incorrect conversion to comparable currency at initial check of deposit volume
* For analytic export replace IOT to IOTA for Bitfinex

## v1.2.7 2022-09-18
### Fixed
* If it is not possible to calculate the price overlap for the cycle reverse, its value set to coarse estimate * 2
instead of the OVER_PRICE
* In saved state added StrategyBase.trades. This is for correct restore if order was filled partially

### Update
README.md - renewed installation chapter
 
### Added for new features
* Disconnecting the gRPC server is now safe, auto reconnect with full recovery of the current session

## v1.2.6-8-hotfix 2022-09-03
### Fixed
* [File exist error on Windows 11](https://github.com/DogsTailFarmer/martin-binance/issues/19#issue-1360296628)

## v1.2.6-7 2022-09-01
### Fixed
* Incorrect settings for max grid orders count at grid update (Filter failure: MIN_NOTIONAL)

### Update
* requirements.txt exchanges-wrapper>=1.2.4-5

## v1.2.6 2022-08-27
### Fixed
* [Incomplete account setup](https://github.com/DogsTailFarmer/martin-binance/issues/17#issue-1347470971)

### Update
* up to Python 3.10.6
* 1.2.5-3 update on_place_order_error_string() to avoid the cyclical sending of an order rejected by the exchange
* [Update readme - limit for several pair with intersecting coin](https://github.com/DogsTailFarmer/martin-binance/issues/18#issue-1347575119)

## v1.2.5 2022-08-20
### Fixed
* if not FEE_IN_PAIR and Reverse: underreporting of income as a result of excess fee accrual

### Update
* calculate round quote pattern
* optimize place grid method

### Added for new features
* implemented first grid order volume calculating for effective FTX trading

## v1.2.4 Hotfix - 2022-08-15 
### Fixed
* Incorrect calculation TP parameters for TP sell, price < 1, (fee + profit) amount < step_size

## v1.2.3 - 2022-08-14
### Fixed
* [No status reply](https://github.com/DogsTailFarmer/martin-binance/issues/11#issue-1328210503)
* [Stopped command in last state when low RAM](https://github.com/DogsTailFarmer/martin-binance/issues/14#issue-1333292978)

### Added for new features
* Protect against OS failures when saving a state file
* [No help it Telegram bot](https://github.com/DogsTailFarmer/martin-binance/issues/8#issue-1315732905)
For Telegram bot set up command menu and online help

### Update
* Dependencies
* Refactoring calculate TP
* Refactoring calculate over price

## v1.2.2 - 2022-08-08
### Update
* Add \n on each input request
* Handling HTTP 429 error for coinmarketcap

## v1.2.1 - 2022-08-07
### Fixed
* Restore strategy from saved state after restart - get and handling missed event before the state was loaded
* Max retries exceeded with url: * for Telegram requests.post()

### Update
* After restart save previous last state file into .bak

## v1.2.0 - 2022-08-04
### Added for new features
* Bitfinex exchange for STANDALONE mode added
* Control for first and last grid orders volume added
* For `ex.STATUS_DELAY = 5  # Minute between sending Tlg message about current status, 0 - disable` parameter add
ability to turn off

### Fixed
* Correct rounding for base and quote assets on different exchanges

### Update
* Refactoring method for calculate over price in Reverse cycle
* Up https://pro.coinmarketcap.com API call to v2

If you update from lower versions please change reference in
`martin_binance/ms_cfg.toml` on next:

    `# CoinMarketCap`

    `url = "https://pro-api.coinmarketcap.com/v2/tools/price-conversion"`

* ATTENTION: in the required package `exchanges-wrapper` was changed format config file
`exchanges_wrapper/exch_srv_cfg.toml` from 1.2.0 version. Before update, save old file and transfer configuration
data into new.
* Finished implemented Decimal calculation for orders processing
* Change data type for `REVERSE_TARGET_AMOUNT` parameter in `cli_XX_AAABBB.py`, update it before restart
* Renewed Grafana template

## v1.1.0 - 2022-06-16
### Added for new features
* FTX exchange for STANDALONE mode added
* updating grid if market conditions change

### Update
* Grafana template
* code refactoring

## v1.0rc7 - 2022-03-01
### Added for new features
* control and structure update for funds_rate.db for future updates
* alerting for mismatch of number of orders to strategy status

### Fixed
* updated balance value for direct cycle for analytics

### Update
* refined calculation of order parameters for grid, taking into account rounding of price and volume value and
correction of parameters of the last order
* Binance API for /api/v3/exchangeInfo

## v1.0rc6.1 - 2022-01-19
### Update
* refactoring funds_rate_exporter.py
* readme.md, add 'For developer' chapter

## v1.0rc6 - 2022-01-11
### Fixed
* handler for cancel order - part filled - correct cancel non-filled part 
* release hold grid after check, not place grid
* remove extra messages about receiving the command through the Telegram
* incorrect balance in USD for assets in trading pair (for analytics)

### Update
* set min profit for TP also when calculate it before reverse
* Grafana dashboard template, some improvement

### Added for new features
* some cycle parameters for export into analytic
* STANDALONE mode (Binance) get asset balances from Funding wallet for analytics

## v1.0rc5 - 2021-12-27
### Fixed
* Set min profit for TP when executing only the penultimate order of the grid

### Added for new features
* Modified and tested for macOS

## v1.0rc4 - 2021-12-23
### Update
* Readme.md

### Added for new features
* Cycle end alert and manual action waiting
* Set min profit for TP when executing the penultimate order of the grid

### Fixed
* TypeError: unsupported operand type(s) for -: 'float' and 'NoneType' At: /executor.py(615):


## v1.0rc2 - 2021-12-21
### Fixed
* margin Windows full functional
* refactoring service process threading

## v1.0rc0 - 2021-12-07
* Added direct access to Binance SPOT API
* Migrate to Decimal() calculation for necessary precision
* Added stop-loss checkpoint for possible bug
* Split logic and initial trading setup
* Added buy/sell asset with grid options

### Fixed
* Full code refactoring

### Update
* Readme.md

## v0.8rc - 2021-07-29
### Added for new features.
* Auto calculate round float multiplier
* Added fee processing for second currency only, like as KRAKEN
* For analytic subsystem added consolidated asset valuation
* Additional check for Error when place and cancel order
* Recovery state logic implemented
* For ADAPTIVE_TRADE_CONDITION adaptive calculate grid orders quantity

### Fixed
* Message 'Waiting ending cycle for manual action' instead of 'Stop...'

### Changed for existing functionality.
* Code refactoring
* Place grid orders by part block for first ORDER_Q count and one by one for next

### Update
* Readme.md

## v0.7rc - 2021-06-04
### Added for new features.
* Send Telegram messages periodically that bot still alive
* Added adaptive profit calculate based on Bollinger band
* Added config for [prometheus_client](https://github.com/prometheus/client_python)
* Added 'no loss' over price calculate for Reverse cycle grid
* Added Average Directional Index analysis to optimize Reverse solution

### Fixed
* Difference k for top and bottom BB line

### Update
* Readme.md

## v0.5b - 2021-06-08
### Added for new features
* Calculate price of grid orders by logarithmic scale
* Added cycle result data for save into t_funds

### Update
* Readme.md

### Fixed
* Refactoring and optimise calculate and place take profit order
* Optimise saving funds and cycle data to .db

## v0.4b - 2021-05-29
### Added for new features.
* Check if the take profit order execute by market and process it
* Optimize send Telegram message and save to .db function

## v0.3b - 2021-05-28
### Added for new features.
* Create public edition

## v0.2b - 2021-05-28
### Fixed
* Fix funds call error

### Added for new features.
* Commented service functions
* Added setup info into docstring

## v0.7a - 2021-05-26
### Added for new features.
* External control from Telegram bot

## v0.6a - 2021-05-23

### Added for new features
### Changed for changes in existing functionality
### Deprecated for soon-to-be removed features
### Removed for now removed features
### Fixed for any bug fixes
### Security 

