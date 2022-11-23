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

