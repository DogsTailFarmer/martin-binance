## v1.0rc0 - 2021-12-07
* Added direct access to Binance SPOT API
* Migrate to Decimal() calculation for best precision
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
* Check if take profit order execute by market and process it
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

### Added for new features.
### Changed for changes in existing functionality.
### Deprecated for soon-to-be removed features.
### Removed for now removed features.
### Fixed for any bug fixes.
### Security 

