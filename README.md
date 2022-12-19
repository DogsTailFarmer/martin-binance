<p align="center"><img src="https://github.com/DogsTailFarmer/martin-binance/raw/public/doc/Modified%20martingale.svg" width="300"></p>

***
<h1 align="center">Modified Martingale</h1>

<h2 align="center">Cyclic grid strategy for SPOT market</h2>

<h3 align="center">Free trading system for crypto exchanges (Binance, Bitfinex, Huobi, OKX,)</h3>

<h4 align="center">Other crypto exchanges available through multi-exchange terminal <a href="#margin">margin.de</a></h4>

***
<h4 align="center">martin-binance <a href="https://badge.fury.io/py/martin-binance"><img src="https://badge.fury.io/py/martin-binance.svg" alt="PyPI version" height="20"></a> <--> exchanges-wrapper <a href="https://badge.fury.io/py/exchanges-wrapper"><img src="https://badge.fury.io/py/exchanges-wrapper.svg" alt="PyPI version" height="20"></a></h4>

***
<h1 align="center"><a href="https://codeclimate.com/github/DogsTailFarmer/martin-binance/maintainability"><img src="https://api.codeclimate.com/v1/badges/bfa43f47d1c9a385fd8a/maintainability"/></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/martin-binance/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/martin-binance.svg/?label=resolved+issues&token=ONJLSJHeeBvXyuaAjG1OWUhG"/></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/martin-binance/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/martin-binance.svg/?label=active+issues&token=ONJLSJHeeBvXyuaAjG1OWUhG"/></a>
<a href="https://lgtm.com/projects/g/DogsTailFarmer/martin-binance/alerts/"><img alt="Total alerts" src="https://img.shields.io/lgtm/alerts/g/DogsTailFarmer/martin-binance.svg?logo=lgtm&logoWidth=18"/></a>
<a href="https://lgtm.com/projects/g/DogsTailFarmer/martin-binance/context:python"><img alt="Language grade: Python" src="https://img.shields.io/lgtm/grade/python/g/DogsTailFarmer/martin-binance.svg?logo=lgtm&logoWidth=18"/></a>
<a href="https://sonarcloud.io/summary/new_code?id=DogsTailFarmer_martin-binance" target="_blank"><img alt="sonarcloud" title="sonarcloud" src="https://sonarcloud.io/api/project_badges/measure?project=DogsTailFarmer_martin-binance&metric=alert_status"/></a>
<a href="https://pepy.tech/project/martin-binance" target="_blank"><img alt="Downloads" title="Downloads" src="https://pepy.tech/badge/martin-binance/month"/></a>
</h1>

***
## The motto of the project

**_Profitable, fault-tolerant, adaptable to the market. Started and forgot._**
*Don't forget to pick up what you earned.*

Regardless of any trend, exchange overloads, network connection lost, hardware fault.

## Disclaimer

All risks and possible losses associated with use of this strategy lie with you.
Strongly recommended that you test the strategy in the demo mode before using real bidding.

## Important notices
* 1.2.9 Before use Huobi exchange update ```/home/ubuntu/.MartinBinance/config/exch_srv_cfg.toml``` to last ver. from ```exchanges-wrapper/exch_srv_cfg.toml.template```
* You cannot run multiple pairs with overlapping currencies on the same account!

>Valid: (BTC/USDT), (ETH/BUSD), (SOL/LTC)
> 
>Incorrectly: (BTC/USDT), (ETH/USDT), (BTC/ETH)
> 
>As a result of the mutual impact on the operating balance sheet, the liquidity control system will block the work.

## Review
<p align="center"><img src="https://gist.githubusercontent.com/DogsTailFarmer/b650b9b199666700d2839fb46d3aa1d7/raw/657ea8e7ad79df66d9d373776aeeb8614241f03f/architecture.svg"></p>

Starting with version 1.1.0 the project was transformed into two parts:
* Crypto exchanges API/WSS async wrapper with grpc powered server [exchanges-wrapper](https://github.com/DogsTailFarmer/exchanges-wrapper)
* This package, a ready-to-use trading strategy that also can be used as a template for implementing your own ideas.

The system has two modes:
* STANDALONE, for free unlimited trading on crypto exchanges SPOT market.
* python_strategy modules can be used as plug-in trading strategy for multi-exchange terminal
<a href="#margin">margin.de</a>, free demo, you can try it.

Strategy logic realized at executor.py and trading parameters settings in the cli_1_AAABBB.py (cli_7_BTCUSDT.py)

You can modify them for your needs. See <a href="#for-developers">For developers</a> section.

## Reference

<a href="#trade-idea">Trade idea</a>

<a href="#features">Features</a>

<a href="#quick-start">Quick start</a>

<a href="#add-new-exchange-account">Add new exchange account</a>

<a href="#tmux">Terminal Tmux for STANDALONE mode</a>

<a href="#how-its-work">How it's work</a>

<a href="#for-developers">For developers</a>

<a href="#known-issue">Known issue</a>

<a href="#target">Target</a>

<a href="#referral-link">Referral code and donat</a>

## Trade idea
<p id="trade-idea"></p>

<p align="center"><img src="https://user-images.githubusercontent.com/77513676/191544694-21f28b6f-9d6c-4258-b686-c29653dc9c77.png"></p>

Create a grid of increasing volume orders and when they perform
creation of one take profit order in the opposite direction.

Its volume is equal to the sum of the executed grid orders,
and the price compensates the fee and provides the specified profit.

What is the chip? After each grid order executed, the price of the take profit order (TP)
approaches the price of the grid, which requires less bounce to perform it.

If all grid orders filled, then reverse and start the cycle in another direction.
The price overlap set for the reverse cycle grid provides a given profit for the initiating cycle.

For Reverse cycle there are only two possible result depending on the price in the market.
In the first case the entire grid executed therefore we close the previous cycle with profit.
In second case executing part of the grid orders, and the filling take profit order increase the depo in the second coin.
It reduces the necessary price overlap and sooner or later first variant comes true.

This allows you to increase the initial deposit using price fluctuations in any trend,
and makes this strategy really break even. Unless you trade scam shitcoin.

In the cycle to sell, the profit accumulates in the first currency.
In the cycle to buy, the profit accumulates in the second coin.

Fee payments are taken into account when calculating TP.

The optimal pair choice is a stable coin or fiat plus a coin from the top ten.

## Features
<p id="features"></p>

* Create grid and take profit orders
* Logarithm price option for grid orders (customizable)
* Reverse algo if all grid orders are filling
* Calculation of the price overlap for the Reverse cycle for the profitable completion of the previous cycle
* Use Average Directional Index indicator for best time starting Reverse cycle
* Calculation of separate MAKER and TAKER fee
* Shift grid orders (customizable) if the price is go way (before take profit placed)
* Adapted size of the first order depending on the exchange's limitations
* Fractional creation of grid for increase productivity (customizable)
* Adaptive overlap price for grid on current market conditions (customizable) based on Bollinger Band
* Update grid orders if market conditions change
* Adaptive profit setting on current market conditions (customizable) based on Bollinger Band
* Adaptive grid orders quantity for initial and Reverse cycle
* Stable operation in pump/dump conditions
* Process partial execution of orders with large amounts of funds
* Save funding change, cycle parameter and result in sqlite3 .db for external analytics
* Telegram notification
* External control from Telegram bot
* Restore state after restart strategy
* From 1.2.9-8 you can withdraw and deposit assets on active strategy with autocorrection depo and initial assets
control values

## Quick start
<p id="quick-start"></p>

For STANDALONE mode you can use both - pip and Docker deployment schemas, as you choice.

For *margin* mode - pip only.

#### Create Telegram bot
* Register [Telegram bot](https://t.me/BotFather)
* Get token
* Find channel_id. Just start [IDBot](https://t.me/username_to_id_bot) and get channel_id
* After next step specify this data into ```/home/ubuntu/.MartinBinance/config/ms_cfg.toml``` for 'Demo - Binance', 7

### Docker
* Install and run [exchanges-wrapper](https://github.com/DogsTailFarmer/exchanges-wrapper#get-started) server.
* Pull last version of martin-binance image
```console
docker pull ghcr.io/dogstailfarmer/martin-binance:latest
```

#### First run
The structure of the working directory will be created and the necessary files will be copied:
For Ubuntu it will be here: ```home/user/.MartinBinance/```
```console
docker run --rm --entrypoint /bin/sh martin-binance -c "cat ./martin_binance/__init__.py" > init.py && \
  docker run --rm --entrypoint /bin/sh martin-binance -c "cat ./martin_binance/ms_cfg.toml.template" > ms_cfg.toml.template &&\
  docker run --rm --entrypoint /bin/sh martin-binance -c "cat ./martin_binance/funds_rate.db.template" > funds_rate.db.template &&\
  docker run --rm --entrypoint /bin/sh martin-binance -c "cat ./martin_binance/cli_7_BTCUSDT.py.template" > cli_7_BTCUSDT.py.template &&\
  docker run --rm --entrypoint /bin/sh martin-binance -c "cat ./martin_binance/cli_10_AAABBB.py.template" > cli_10_AAABBB.py.template &&\
  python3 init.py && rm init.py && rm ms_cfg.toml.template && rm funds_rate.db.template && rm cli_7_BTCUSDT.py.template && rm cli_10_AAABBB.py.template
```
#### Start client
```console
docker run -itP \
 --mount type=bind,source=/home/ubuntu/.MartinBinance,target=/home/appuser/.MartinBinance \
 --network=host \
 --restart=always \
 --name=7-BTCUSDT \
 martin-binance \
 /home/appuser/.MartinBinance/cli_7_BTCUSDT.py 1
```
The last '1' it is parameter for silent restart with restore operational status.

```.MartinBinance/cli_7_BTCUSDT.py``` where trading parameters must be setting.

For auto update running containers recommended use [Watchtower](https://github.com/containrrr/watchtower/)

### Install from pip

```console
pip install martin-binance==1.2.11b1
```
After first install find where pip installs packages, often it's ```/home/ubuntu/.local/lib/python3.10/site-packages```
and run:
```console
exchanges_wrapper/__init__.py
```
then
```console
martin_binance/__init__.py
```
The structure of the working directory will be created and the necessary files will be copied. On __init__ output
you can find location.

#### Start server
* Specify api_key and api_secret in ```/home/ubuntu/.MartinBinance/config/exch_srv_cfg.toml```
* Run ```exchanges_wrapper/exch_srv.py``` in terminal window.

#### Start client
* Run ```/home/ubuntu/.MartinBinance/cli_7_BTCUSDT.py``` in other terminal window.

Strategy is started.

For upgrade to latest versions use:
```console
pip install -U martin-binance
```

#### Setting trade pair
You must set pair name in three places the same (yes, it is crooked, but so far):
* base setting at top of the ```cli_X_AAABBB.py```, ```ex.SYMBOL = 'AAABBB'```
* the name of ```cli_X_AAABBB.py``` must match
* the ```X``` it is index of element from exchange list in ```config/ms_cfg.toml```

>For 'Demo - Binance' and BTC/USDT trade pair it will be cli_7_BTCUSDT.py

* the name of pane in <a href="#tmux">Tmux terminal window</a> must match too, see explanation in the relevant section

For stop strategy use Ctrl-C and/or Telegram control function

### MARGIN mode
*For different OS paths will be different, this example for Ubuntu*

* Install [margin](https://margin.de/download/) to the ```~/opt/margin/```

Change dir to the ```~/opt/margin/resources/python/lib/python3.7/site-packages/``` and install martin-binance there:
```console
pip install --no-cache-dir -t . -U --ignore-requires-python --no-deps martin-binance==1.2.11b1
```
The margin terminal uses its own assembly Python3.7 which does not have some packages necessary for the strategy
to work. They need to be installed.

For Ubuntu (Linux):
```console
pip install --no-cache-dir -t . -U --ignore-requires-python --no-deps -r ./martin_binance/margin/margin_req.txt
```
*For Ubuntu (Linux) check if exist file*
```~/opt/margin/resources/python/lib/python3.7/lib-dynload/_sqlite3.cpython-37m-x86_64-linux-gnu.so```
and if not, copy it from ```martin_binance/margin/_sqlite3.cpython-37m-x86_64-linux-gnu.so```

For Windows:
```console
pip install -U wheel
```
```console
pip install -U setuptools
```
```console
pip install --use-pep517 --no-cache-dir -t . -U --ignore-requires-python --no-deps -r ./martin_binance/margin/margin_req_win.txt
```
*For Windows* download file [margin_win_addon.zip](https://github.com/DogsTailFarmer/martin-binance/files/10262282/margin_win_addon.zip)
and unzip it to the ```C:\Users\UserName\AppData\Local\Programs\margin\resources\python\lib\python3.7\site-packages```
if margin installed in that place or find it yourself
***
After first install run
```
site-packages/martin_binance/__init__.py
```
The structure of the working directory will be created and the necessary files will be copied. On __init__ output
you can find location.

* Create Telegram bot as described above and specify the data in ```ms_cfg.toml```
***
* Start margin in Demo mode
* Add currency pair BTC/USDT
* Set the custom fee level = 0.0% in the margin terminal settings
* Add Python strategy:
<p align="center"><img src="https://git.io/JDIiQ"></p>

* Copy/paste the contents of the file ```/home/ubuntu/.MartinBinance/cli_7_BTCUSDT.py``` to the Code Editor window
* Save, Run Strategy, Start

Strategy is started.

#### Setting trade pair
The selection of the pair is determined by the window of the terminal in which the strategy is launched.

### Add new exchange account (STANDALONE mode)
<p id="add-new-exchange-account"></p>
Adding an account is in two parts

* For server, it is ```/home/ubuntu/.MartinBinance/config/exch_srv_cfg.toml```,
where you place API key and *account name*
* For client, it's ```/home/ubuntu/.MartinBinance/config/ms_cfg.toml```,
where you add *account name* into exchange list and setup Telegram parameters

The *account name* _must_ be identically for server and client configs.

## Terminal Tmux (Linux)
<p id="tmux"></p>
For STANDALONE mode you need separate terminal window for each task, separate for server and for each trading pair.
If you plan to run a strategy on VPS then you need terminal program which:

* multi windows/panes
* continue running after end of ssh session
* auto save running state
* restore state after system restart

The [Tmux](https://github.com/tmux/tmux) meets all these requirements.
 
### Tmux install
Install and setup all in list:

* [Tmux](https://github.com/tmux/tmux)
* [Tmux Plugin Manager](https://github.com/tmux-plugins/tpm#tmux-plugin-manager)
* [Tmux sensible](https://github.com/tmux-plugins/tmux-sensible)
* [Tmux Resurrect](https://github.com/tmux-plugins/tmux-resurrect)
* [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum)

Find /service/tmux.service, edit your path and install it under systemctl. 

Example for tmux configuration file .tmux.conf
~~~
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-sensible'
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @continuum-restore 'on'
set -g @continuum-save-interval '15'
set -g @continuum-boot 'on'
set -g status-right 'Status: #{continuum_status}'
set -g assume-paste-time 1
set -g base-index 0
set -g bell-action none
set -g history-file ~/.tmux_history
set -g mouse on
set -g prefix C-b
run '~/.tmux/plugins/tpm/tpm'
~~~

Attention: The name of session ('Trade') and pane ('srv', '7-BTC/USDT') must be same as in example and correspond pair
which start in this pane. For example cli_1_BTCUSDT.py must be started in pane with name '1-BTC/USDT'

* Start new session:
~~~
tmux new-session -s Trade
~~~
* Rename pane 0: Ctrl+B + , srv Enter
* Change dir to the ```~/.local/lib/python3.8/site-packages/exchanges_wrapper```
* Create new pane: Ctrl+B c
* Rename pane 1: Ctrl+B + , 7-BTC/USDT Enter
* Change dir to the ```~/.MartinBinance```
* Reboot system
* Attach to the restored session:
~~~
tmux attach
~~~
You must see the same window as before reboot:

<p align="center"><img src="https://git.io/JDIix"></p>

For each pane appropriate dir must be selected.

* Find /service/relaunch.service, edit your path and install it under systemctl.
* Run in the pane 0:srv server script:
~~~
./exch_srv.py
~~~
* Run in the pane 1:7-BTC/USDT trade strategy script:
~~~
./cli_7_BTCUSDT.py
~~~

Final test, reboot system. After reboot connect to the tmux session:
~~~
tmux attach
~~~
If everything has been done correctly you should see the restored strategy.

## How it's work
<p id="how-its-work"></p>

_Setup all mentioned trade parameter at the top of cli_X_AAABBB.py_

Where X is exchange number, see it in ms_cfg.toml and AAABBB is trade pair, for example BTCUSDT on Binance is cli_9_BTCUSDT.py

<a href="#place-grid">Place grid</a>

<a href="#shift-grid-orders">Shift grid orders</a>

<a href="#adaptive-overlap-price-for-grid">Adaptive overlap price for grid</a>

<a href="#quantity-of-grid-orders">Quantity of grid orders</a>

<a href="#fractional-creation-of-grid">Fractional creation of grid</a>

<a href="#logarithm-price-option">Logarithm price option</a>

<a href="#reverse">Reverse</a>

<a href="#grid-only">Grid only</a>

<a href="#place-take-profit">Place take profit order</a>

<a href="#restart">Restart</a>

<a href="#fee-options">Fee options</a>

<a href="#deposit-and-withdraw-assets-on-active-strategy">Deposit and withdraw assets on active strategy</a>

<a href="#telegram-notification">Telegram notification</a>

<a href="#telegram-control">Telegram control</a>

<a href="#save-data-for-external-analytics">Save data for external analytics</a>

<a href="#consolidated-asset-valuation">Consolidated asset valuation</a>

<a href="#recovery-after-any-reason-crash">Recovery after any reason crash, restart etc.</a>


### Place grid
<p id="place-grid"></p>

The main parameters for the strategy are grid parameters. Specify the trade direction for the first cycle.
If START_ON_BUY = True, a grid of buy orders will be placed and take profit will be for sale.

Specify the deposit size for the first cycle in the desired currency, and the number of grid orders.
These are related parameters, there is a limit on the minimum size of the order,
so a many orders if the deposit is insufficient will not pass the verification during initialization.

The size of the order in the grid calculated according to the law of geometric progression,
while the MARTIN parameter is a coefficient of progression.
The first order, the price of which is closest to the current one is the smallest in volume.

To avoid the execution of the first order "by market" its price set with a slight offset,
which is determined by the parameter PRICE_SHIFT.

#### Shift grid orders
<p id="shift-grid-orders"></p>

It happens that when place a grid, the price goes in the opposite direction. There is no point
in waiting in this case, we need to move the grid after the price.
For this there are SHIFT_GRID_DELAY. Configure them or leave the default values.

#### Adaptive overlap price for grid
<p id="adaptive-overlap-price-for-grid"></p>

The range of prices that overlaps the grid of orders affects profitability directly 
and must correspond to market conditions. If it is too wide combined with small number of orders,
the cycle time will be too long, and most of the deposit will not be involved in turnover.
With a small overlap, the entire order grid will be executed in a short time, and the algorithm will be reversed,
while the profit on the cycle not fixed.

The overlap range can be fixed. Then it is defined by OVER_PRICE = xx and ADAPTIVE_TRADE_CONDITION = False.

For automatic market adjustment, ADAPTIVE_TRADE_CONDITION = True. In this case, the instant value
of the Bollinger Band on 20 * 1 hour candles used to calculate the overlap range. The minimum values
are limited by the exchange limit for minimal price change per one step combined with number of orders.

For fine-tuning there is KBB parameter. By default, value 2.0 is used to calculate Bollinger curves.

The over price value update before the start of the new cycle and periodically refreshed.
If the market condition change exceeds the set limits, the grid is updated (does not apply in reverse cycle).

#### Quantity of grid orders
<p id="quantity-of-grid-orders"></p>

Two parameters determine the number of orders, ORDER_Q and OVER_PRICE. For start cycle and parameter
ADAPTIVE_TRADE_CONDITION = False, these are absolute and fixed values.

For Reverse cycle or parameter ADAPTIVE_TRADE_CONDITION = True they specify the density of grid orders.
At the same time, the larger the range of overlap, the more orders there will be.
When calculating, the exchange's restrictions on the minimum order size and price step taken into account
and thus limit the maximum number of orders.

For Reverse cycle, this is especially important, since with large price fluctuations we will have to sweep
a very large range, 30-50% or more. In which case an adaptive number of orders will allow to do this as efficiently
as possible.

#### Fractional creation of grid
<p id="fractional-creation-of-grid"></p>

For successful trading, the speed of the bot response to price fluctuations is important.
When testing on Bitfinex, I noticed that when placed a group of orders,
the first 5 are placed quickly, and the remaining ones with a significant delay. Also, the more orders,
the longer it takes to shift the grid.

Therefore, I added the parameter GRID_MAX_COUNT, which specifies the number of initial orders to be placed.
Then, two options performed. First, the grid shift function triggered. Second, one of the placed grid orders executed,
and after successful creation of the take profit order, the next part *GRID_MAX_COUNT* of hold grid orders added.
If total count of active grid orders more than ORDER_Q and hold grid not exhaust each next placed one
after filling one grid order, until the hold list exhausted.
 
Thus, we always have a given number of active orders to respond to price fluctuations and have a large range
of price overlap. Then, we do not risk running into the ban from exchange for exceeding the limit.

#### Logarithm price option
<p id="logarithm-price-option"></p>

You can increase the share of the deposit in turnover when calculating the price for grid orders using not a linear,
but a logarithmic distribution. The density of orders near the current price will be higher,
which increases the likelihood of their execution.

Use LINEAR_GRID_K parameter and see '/doc/Model of logarithmic grid.ods' for detail.

### Reverse
<p id="reverse"></p>

It happens that all grid orders completed. Then we believe that we successfully bought the asset,
and place a take profit order. Instead of one order, we place a grid, which ensures the break-even strategy.
The grid parameters change dynamically, depending on the market conditions, accumulated deposit
during execution of the Reverse cycle, and the specified profitability parameters.

With each successful completion of the reverse cycle, the accumulated profit volume increases,
which reduces the necessary price overlap for the profitable completion of the original cycle.

In order for the algorithm not to work for itself in reverse mode, only part of the earned profit is reinvested.
PROFIT_REVERSE parameter specifies the reinvestment rule. Leave it as default.

### Grid only
<p id="grid-only"></p>

You can buy/sell asset with grid options. To do this, set the GRID_ONLY = True
In this case, the take-profit order will not be placed and Reverse cycle not started. After filling all grid orders
strategy goes to STOP state. All options associated with grid calculation work as usual, except no shifting grid.

### Place take profit
<p id="place-take-profit"></p>

As the grid orders executed, the volume of the take profit order sums up their volume,
price averaged and increased to override the fees and earn the specified profit.

Do not set PROFIT too large. This reduces the probability of executing a take profit order
with small price fluctuations. I settled on a value of about 0.5%

For adaptive calculate profit before place order you can set PROFIT_MAX.
Then its value will be set in the range from PROFIT to PROFIT_MAX. Calculation based on Bollinger Band
indicator with PROFIT_K coefficient.

### Restart
<p id="restart"></p>

When take profit order executed the cycle results recorded, the deposit increased by the cycle profit,
and bot restarted.

### Fee options
<p id="fee-options"></p>

To correctly count fees for MAKER and TAKER, you must set the FEE_MAKER and FEE_TAKER parameters.

For a third currency fee, such as BNB on Binance, or HT on Huobi, set FEE_IN_PAIR = False

For fee processing for second currency only, like as KRAKEN, use FEE_SECOND = True

Priority of parameters from larger to smaller is:
* FEE_IN_PAIR 
* FEE_BNB_IN_PAIR
* FEE_SECOND

Attention: the commission, which is charged in the third coin, is not taken into account in the calculation of income.
Control the return on the balance of three coins.

### Deposit and withdraw assets on active strategy
<p id="deposit-and-withdraw-assets-on-active-strategy"></p>

It is better to change the assets amount for the strategy when it has completed the cycle and stopped. However,
subject to the following conditions and restrictions and some luck, you can do this on a running strategy.

Limits there are next:
* strategy must be in "stable state". This means that the grid and take profit order are placed and the current price is
equidistant from them.
* Before withdrawing you must get actual info about Free assets (find it on status report in Telegram)

*Deposit* asset: For Reverse cycle the increase in the current deposit volume does not occur, the added volume will be
taken into account as free. For a direct cycle, the deposit will be increased for the second currency in the Buy cycle
and for the first in the Sell cycle.

*Withdraw* asset: If all grid orders and take profit order are placed, then only free assets that are not involved
in the turnover are available for withdrawal. If some orders are held, you may accidentally withdraw the asset
necessary for their placement. In this case, you will receive a warning.

Use the exchange tools for I/O funds, the necessary and possible adjustments will be made automatically.

### Telegram notification
<p id="telegram-notification"></p>

Basic information about the state of the bot, for example, about the start and results of the cycle,
can be sent to Telegram bot.

<p align="center"><img src="https://user-images.githubusercontent.com/77513676/198888456-5d1af806-d0f3-42dd-be03-dad57669e6a7.png"></p>

### Telegram control
<p id="telegram-control"></p>

* status - get current status
* stop - stop after end of cycle (if current cycle is reverse - only after back to direct cycle)
* end - stop after end of cycle, direct and reverse, no difference

All commands are sent as a reply to message from desired strategy. Use simple text message or menu items. For use menu 
after first run strategy in Telegram bot use /start command once.
If all is normal, you will receive a confirmation that the system has received the command within 10 seconds.

### Save data for external analytics
<p id="save-data-for-external-analytics"></p>

Analytic subsystem is not mandatory and has no impact on trading strategy.

All data collected into ```funds_rate.db```

Cycle time, yield, funds, initial cycle parameters, all this for all pairs and exchanges where this bot launched.

In STANDALONE mode for Binance also collected all balances for all assets in trading account. 

It Sqlite3 db with very simple structure, in table t_funds each row is the result of one
cycle with parameters and result.

Now I'm use [prometheus](https://github.com/prometheus/client_python) -> [Grafana](https://grafana.com/)
for calculate and visualisation analytic data. It's useful. You can use funds_rate_exporter.py for start.
Find it into repository. 

Also, you can try the ```martin_binance/service/grafana.json``` as example of consolidated report.

### Consolidated asset valuation
<p id="consolidated-asset-valuation"></p>

If you have several trading pairs on different exchanges, then regular valuation of the asset is a very time-consuming
task.

<p align="center"><img src="https://git.io/JDIPt"></p>

At the end of each trading cycle, deposit data recorded for each currency. Once a day, the current currency rate to USD
is queried. In ```funds_rate_exporter.py``` of times per minute calculated data for unloading in
[prometheus](https://github.com/prometheus/client_python). An example of a summary report implemented on Grafana
located above.

To receive quotes, you need to get the free API key on [CoinMarketCap](https://coinmarketcap.com/api/pricing/).
Specify the key at the top of the ms_cfg.toml and start ```funds_rate_exporter.py``` as service. For Ubuntu,
you can use ```/service/funds_export.service``` 

### Recovery after any reason crash, restart etc.
<p id="recovery-after-any-reason-crash"></p>

#### STANDALONE mode
* Auto for Network failure, exchange timeout etc. 
* Auto recovery after restart with full implemented Tmux install (Linux only)
* For manual restart with save order and load last state run ```./cli_X_AAABBB.py 1```

#### margin mode
* Network failure, timeout etc.

This is margin layer does, and it's work good. No additional action from user needed.

* Hard restart.

Margin periodically, every two seconds, save strategy state, and after restart place strategy in suspend state.
Strategy check if some order filled out during inactivity and recalculate state for normal operation. You need
manual unsuspend strategy for further work.

This will work well if, at the time of interruption, the strategy was in a stable state and there were
not pending actions to place/remove orders. Processing such situations requires research,
and I am not sure that it is necessary.
  
* Maintenance

If you need setup new version margin or Python strategy, first you need stop strategy.
Use Telegram control function, described above.

## For developers
<p id="for-developers"></p>

The modular open architecture of the project allows you to use it both as a ready-made solution and in parts when
developing your own strategies. See Review chart for reference.

Warning.
Coverage of overridden [margin strategy-sdk](https://github.com/MarginOpenSource/strategy-sdk) is significant but not complete.
Only methods and functions required for normal operation of the presented strategy are implemented.
Missing functionality can be implemented on yours own or on request.

### Easy way
If you want to develop 'margin style' strategy, use
[template](https://github.com/MarginOpenSource/strategy-template) from margin repository.  In this way you can use it
both independently (STANDALONE mode) and together with [margin.de](https://margin.de)

### Independent way
A fully independent strategy that can be used on exchanges that are supported by the
[exchanges-wrapper](https://github.com/DogsTailFarmer/exchanges-wrapper). Description and examples of use referenced above.

## Known issue
<p id="known-issue"></p>

_STANDALONE_ mode:

* None

_With margin.de:_
* Not work more than one Python bot at the same time with "pure virtual function" error after some time.
You can use new instance for new pair
* Sometimes skips the partial fill signal from the margin layer
* Sometimes fill signal from the margin come with a delay, for temp fix use EXTRA_CHECK_ORDER_STATE = True
* When you STOP strategy from margin terminal, close and then restart it, the strategy is started without approval and
restore (can be duplicated) orders. If you want planed restart martin-binance - delete state.db in./margin folder before restart.

## Target
<p id="target"></p>

* Extended testing capabilities
* Optimization ideas
* Several users raise reaction from margin support
* Resources for development
* Get fault tolerance profitable system

## Referral link
<p id="referral-link"></p>

Create account on [Binance](https://accounts.binance.com/en/register?ref=QCS4OGWR) and get 10% discount on all trading
fee

Create account on [HUOBI](https://www.huobi.com/en-us/topic/double-reward/?invite_code=9uaw3223) and get 10% cashback
on all trading fee

Create account on [Bitfinex](https://www.bitfinex.com/sign-up?refcode=v_4az2nCP) and get 6% rebate fee


Create account on [OKEX](https://www.okex.com/join/2607649) and get Mystery Boxes worth up to $10,000

### margin.de
<p id="margin"></p>

Multi-exchange trade terminal. For 10% discount on [margin license](https://margin.de) use coupon code **Margin9ateuE**

#### VPS
Also, you can start strategy on [Hetzner](https://hetzner.cloud/?ref=uFdrF8nsdGMc) cloud VPS only for 4.75 € per month

#### Donate
To donate and directly support the project, you can transfer funds to these addresses in Binance:

*BNB*, *BUSD*, *USDT* (BEP20) 0x5b52c6ba862b11318616ee6cef64388618318b92

*USDT* (TRC20) TP1Y43dpY7rrRyTSLaSKDZmFirqvRcpopC
