<p align="center"><img src="https://github.com/DogsTailFarmer/martin-binance/raw/public/doc/Modified%20martingale.svg" width="200"></p>
<h3 align="center">Profitable, fault-tolerant, adaptable to the market</h3>

***
<h1 align="center">Modified Martingale</h1>

<h2 align="center">Cyclic grid strategy for SPOT market</h2>

<h3 align="center">Free trading system for crypto exchanges:</h3>
<h3 align="center">Binance, Bitfinex, Huobi, OKX, Bybit,</h3>

***
<h4 align="center">martin-binance <a href="https://pypi.org/project/martin-binance/"><img src="https://img.shields.io/pypi/v/martin-binance" alt="PyPI version"></a> <--> exchanges-wrapper <a href="https://pypi.org/project/exchanges-wrapper/"><img src="https://img.shields.io/pypi/v/exchanges-wrapper" alt="PyPI version"></a></h4>

***
<h1 align="center"><a href="https://codeclimate.com/github/DogsTailFarmer/martin-binance/maintainability"><img src="https://api.codeclimate.com/v1/badges/bfa43f47d1c9a385fd8a/maintainability"/></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/martin-binance/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/martin-binance.svg/?label=resolved+issues&token=ONJLSJHeeBvXyuaAjG1OWUhG"/></a>
<a href="https://deepsource.io/gh/DogsTailFarmer/martin-binance/?ref=repository-badge}" target="_blank"><img alt="DeepSource" title="DeepSource" src="https://deepsource.io/gh/DogsTailFarmer/martin-binance.svg/?label=active+issues&token=ONJLSJHeeBvXyuaAjG1OWUhG"/></a>
<a href="https://sonarcloud.io/summary/new_code?id=DogsTailFarmer_martin-binance" target="_blank"><img alt="sonarcloud" title="sonarcloud" src="https://sonarcloud.io/api/project_badges/measure?project=DogsTailFarmer_martin-binance&metric=alert_status"/></a>
<a href="https://pepy.tech/project/martin-binance" target="_blank"><img alt="Downloads" title="Downloads" src="https://static.pepy.tech/badge/martin-binance/month"/></a>
</h1>

***
## Disclaimer
All risks and possible losses associated with use of this strategy lie with you.
Strongly recommended that you test the strategy in the demo mode before using real bidding.

## Important notices
* After update to `3.0.1`, the configuration files `cli_XX_AAABBB.py` for all running trading pairs
should be updated. Use templates for reference.

* You cannot run multiple pairs with overlapping currencies on the same account!

>Valid: (BTC/USDT), (ETH/BUSD), (SOL/LTC)
> 
>Incorrectly: (BTC/USDT), (ETH/USDT), (BTC/ETH)
> 
>As a result of the mutual impact on the operating balance sheet, the liquidity control system will block the work.

* Due to a limitation in the implementation of asyncio under Windows, this program cannot be executed. [Use Docker on Windows instead.](https://github.com/DogsTailFarmer/martin-binance/wiki/Quick-start#docker)

## References
* Detailed information about use this strategy placed to [wiki](https://github.com/DogsTailFarmer/martin-binance/wiki)
* [Trade idea](https://github.com/DogsTailFarmer/martin-binance/wiki/Trade-idea)
* [Quick start](https://github.com/DogsTailFarmer/martin-binance/wiki/Quick-start)
* [Back testing and parameters optimization](https://github.com/DogsTailFarmer/martin-binance/wiki/Back-testing-and-parameters-optimization)

## Referral link
<p id="referral-link"></p>

Create account on [Binance](https://accounts.binance.com/en/register?ref=QCS4OGWR) and get 10% discount on all trading fee

Create account on [HUOBI](https://www.huobi.com/en-us/topic/double-reward/?invite_code=9uaw3223) and will get 50 % off trading fees

Create account on [Bitfinex](https://www.bitfinex.com/sign-up?refcode=v_4az2nCP) and get 6% rebate fee

Create account on [OKEX](https://www.okex.com/join/2607649) and get Mystery Boxes worth up to $10,000

Create account on [Bybit](https://www.bybit.com/invite?ref=9KEW1K) and get exclusive referral rewards

Also, you can start strategy on [Hetzner](https://hetzner.cloud/?ref=uFdrF8nsdGMc) cloud VPS only for 4.75 € per month

### Donate
*USDT* (TRC20) TU3kagV9kxbjuUmEi6bUym5MTXjeM7Tm8K
