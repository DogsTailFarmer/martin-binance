#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple exchange simulator for backtest purpose
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.1.0"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from decimal import Decimal
import pandas as pd


def any2str(_x) -> str:
    return f"{_x:.8f}".rstrip('0').rstrip('.')


class Funds:
    __slots__ = ("base", "quote")

    def __init__(self):
        # {'asset': 'BTC', 'free': '0.0', 'locked': '0.0'}
        self.base = {}
        self.quote = {}

    def get_funds(self):
        return [self.base, self.quote]

    def on_order_created(self, buy: bool, amount: str, price: str):
        if buy:
            self.quote['free'] = str(Decimal(self.quote.get('free', 0)) - Decimal(amount) * Decimal(price))
            self.quote['locked'] = str(Decimal(self.quote.get('locked', 0)) + Decimal(amount) * Decimal(price))
        else:
            self.base['free'] = str(Decimal(self.base.get('free', 0)) - Decimal(amount))
            self.base['locked'] = str(Decimal(self.base.get('locked', 0)) + Decimal(amount))

    def on_order_canceled(self, side: str, amount: str, price: str):
        if side == 'BUY':
            self.quote['free'] = str(Decimal(self.quote.get('free', 0)) + Decimal(amount) * Decimal(price))
            self.quote['locked'] = str(Decimal(self.quote.get('locked', 0)) - Decimal(amount) * Decimal(price))
        else:
            self.base['free'] = str(Decimal(self.base.get('free', 0)) + Decimal(amount))
            self.base['locked'] = str(Decimal(self.base.get('locked', 0)) - Decimal(amount))

    def on_order_filled(self, side: str, amount: str, price: str, fee: Decimal):
        _amount = Decimal(amount)
        _price = Decimal(price)

        base_free = Decimal(self.base.get('free', 0))
        base_locked = Decimal(self.base.get('locked', 0))

        quote_free = Decimal(self.quote.get('free', 0))
        quote_locked = Decimal(self.quote.get('locked', 0))

        if side == 'BUY':
            quote_locked -= _amount * _price
            base_free += _amount - fee * _amount / 100
            self.quote['locked'] = str(quote_locked)
            self.base['free'] = str(base_free)
        else:
            base_locked -= _amount
            quote_free += _amount * _price - fee * (_amount * _price) / 100
            self.base['locked'] = str(base_locked)
            self.quote['free'] = str(quote_free)


class Order:
    __slots__ = (
        "symbol",
        "order_id",
        "order_list_id",
        "client_order_id",
        "transact_time",
        "price",
        "orig_qty",
        "executed_qty",
        "cummulative_quote_qty",
        "status",
        "time_in_force",
        "type",
        "side",
        "working_time",
        "self_trade_prevention_mode",
        "event_time",
        "last_executed_quantity",
        "cumulative_filled_quantity",
        "last_executed_price",
        "trade_id",
        "order_creation_time",
        "quote_asset_transacted",
        "last_quote_asset_transacted",
        "quote_order_quantity",
    )

    def __init__(self, symbol: str, order_id: int, client_order_id: str, buy: bool, amount: str, price: str, lt: int):
        self.symbol = symbol
        self.order_id = order_id
        self.order_list_id = -1
        self.client_order_id = client_order_id
        self.transact_time = lt  # local time
        self.price = price
        self.orig_qty = amount
        self.executed_qty = '0.00000000'
        self.cummulative_quote_qty = '0.00000000'
        self.status = 'NEW'
        self.time_in_force = 'GTC'
        self.type = 'LIMIT'
        self.side = "BUY" if buy else "SELL"
        self.working_time = "-1"
        self.self_trade_prevention_mode = 'NONE'
        #
        self.event_time: int
        self.last_executed_quantity: str
        self.cumulative_filled_quantity: str
        self.last_executed_price: str
        self.trade_id: int
        self.order_creation_time = lt
        self.quote_asset_transacted: str
        self.last_quote_asset_transacted: str
        self.quote_order_quantity: str


class Account:
    __slots__ = (
        "save_ds",
        "funds",
        "fee_maker",
        "fee_taker",
        "orders",
        "orders_buy",
        "orders_sell",
        "trade_id",
        "ticker",
        "grid_buy",
        "grid_sell",
        "ticker_last",
        "market_ids",
    )

    def __init__(self, save_ds: bool):
        self.save_ds = save_ds
        self.funds = Funds()
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')
        self.orders = {}
        self.orders_buy = pd.Series()
        self.orders_sell = pd.Series()
        self.trade_id = 0
        self.ticker = {}
        self.grid_buy = {}
        self.grid_sell = {}
        self.ticker_last = Decimal('0')
        self.market_ids = []

    def create_order(
            self,
            symbol: str,
            client_order_id: str,
            buy: bool,
            amount: str,
            price: str,
            lt: int,
            order_id=None) -> {}:

        order_id = order_id or ((max(self.orders.keys()) + 1) if self.orders else 1)
        order = Order(symbol=symbol,
                      order_id=order_id,
                      client_order_id=client_order_id,
                      buy=buy,
                      amount=amount,
                      price=price,
                      lt=lt)

        if buy:
            self.orders_buy.at[order_id] = Decimal(price)
            if self.save_ds:
                self.grid_buy[lt] = self.orders_buy
        else:
            self.orders_sell.at[order_id] = Decimal(price)
            if self.save_ds:
                self.grid_sell[lt] = self.orders_sell
            #
        self.funds.on_order_created(buy=buy, amount=amount, price=price)
        self.orders[order_id] = order

        if self.ticker_last and ((buy and Decimal(price) >= self.ticker_last) or
                                 (not buy and Decimal(price) <= self.ticker_last)):
            # Market event
            self.market_ids.append(order_id)

        # print(f"create_order.order: {vars(order)}")
        return {'symbol': order.symbol,
                'orderId': order.order_id,
                'orderListId': order.order_list_id,
                'clientOrderId': order.client_order_id,
                'transactTime': order.transact_time,
                'price': order.price,
                'origQty': order.orig_qty,
                'executedQty': order.executed_qty,
                'cummulativeQuoteQty': order.cummulative_quote_qty,
                'status': order.status,
                'timeInForce': order.time_in_force,
                'type': order.type,
                'side': order.side,
                'workingTime': order.working_time,
                'selfTradePreventionMode': order.self_trade_prevention_mode}

    def cancel_order(self, order_id: int, ts: int):
        order = self.orders.get(order_id)
        if order is None:
            raise UserWarning(f"Error on Cancel order, can't find {order_id} anymore")
        order.status = 'CANCELED'
        try:
            if order.side == 'BUY':
                self.orders_buy = self.orders_buy.drop(order_id)
                if self.save_ds and self.orders_buy.values.size:
                    self.grid_buy[ts] = self.orders_buy
            else:
                self.orders_sell = self.orders_sell.drop(order_id)
                if self.save_ds and self.orders_sell.values.size:
                    self.grid_sell[ts] = self.orders_sell
        except Exception as ex:
            raise UserWarning(f"Order {order_id} not active: {ex}") from ex
        else:
            self.orders[order_id] = order
            self.funds.on_order_canceled(order.side, order.orig_qty, order.price)
            return {'symbol': order.symbol,
                    'origClientOrderId': order.client_order_id,
                    'orderId': order.order_id,
                    'orderListId': order.order_list_id,
                    'clientOrderId': 'qwert',
                    'price': order.price,
                    'origQty': order.orig_qty,
                    'executedQty': order.executed_qty,
                    'cummulativeQuoteQty': order.cummulative_quote_qty,
                    'status': order.status,
                    'timeInForce': order.time_in_force,
                    'type': order.type,
                    'side': order.side,
                    'selfTradePreventionMode': order.self_trade_prevention_mode}

    def on_ticker_update(self, ticker: {}, ts: int) -> [dict]:
        # print(f"on_ticker_update.ticker: {ts}: {ticker['lastPrice']}")
        # print(f"BUY: {self.orders_buy}")
        # print(f"SELL: {self.orders_sell}")

        self.ticker_last = Decimal(ticker['lastPrice'])

        orders_id = []
        if self.market_ids:
            orders_id.extend(self.market_ids)
            self.market_ids.clear()

        _i = self.orders_buy[self.orders_buy >= self.ticker_last].index
        self.orders_buy = self.orders_buy.drop(_i.values)
        orders_id.extend(_i.values)

        _i = self.orders_sell[self.orders_sell <= self.ticker_last].index
        self.orders_sell = self.orders_sell.drop(_i.values)
        orders_id.extend(_i.values)

        if self.save_ds:
            # Save data for analytics
            self.ticker[ts] = ticker['lastPrice']
            if self.orders_sell.values.size:
                self.grid_sell[ts] = self.orders_sell
            if self.orders_buy.values.size:
                self.grid_buy[ts] = self.orders_buy
        #
        orders_filled = []
        for order_id in orders_id:
            order = self.orders.get(order_id)
            if order and order.status == 'NEW':
                order.transact_time = int(ticker['closeTime'])
                order.executed_qty = order.orig_qty
                order.cummulative_quote_qty = str(Decimal(order.orig_qty) * Decimal(order.price))
                order.status = 'FILLED'
                order.event_time = order.transact_time
                order.last_executed_quantity = order.orig_qty
                order.cumulative_filled_quantity = order.orig_qty
                order.last_executed_price = order.price
                order.trade_id = self.trade_id = self.trade_id + 1
                order.quote_asset_transacted = order.cummulative_quote_qty
                order.last_quote_asset_transacted = order.cummulative_quote_qty
                order.quote_order_quantity = order.cummulative_quote_qty
                #
                self.orders[order_id] = order
                #
                res = {'event_time': order.event_time,
                       'symbol': order.symbol,
                       'client_order_id': order.client_order_id,
                       'side': order.side,
                       'order_type': order.type,
                       'time_in_force': order.time_in_force,
                       'order_quantity': order.orig_qty,
                       'order_price': order.price,
                       'stop_price': '0.00000000',
                       'iceberg_quantity': '0.00000000',
                       'order_list_id': -1,
                       'original_client_id': order.client_order_id,
                       'execution_type': 'TRADE',
                       'order_status': order.status,
                       'order_reject_reason': 'NONE',
                       'order_id': order_id,
                       'last_executed_quantity': order.last_executed_quantity,
                       'cumulative_filled_quantity': order.cumulative_filled_quantity,
                       'last_executed_price': order.last_executed_price,
                       'commission_amount': '0.00000000',
                       'commission_asset': '',
                       'transaction_time': order.transact_time,
                       'trade_id': order.trade_id,
                       'ignore_a': 12345678,
                       'in_order_book': False,
                       'is_maker_side': True,
                       'ignore_b': True,
                       'order_creation_time': order.order_creation_time,
                       'quote_asset_transacted': order.quote_asset_transacted,
                       'last_quote_asset_transacted': order.last_quote_asset_transacted,
                       'quote_order_quantity': order.quote_order_quantity}
                #
                orders_filled.append(res)
                self.funds.on_order_filled(order.side, order.orig_qty, order.last_executed_price, self.fee_maker)
            #
        return orders_filled

    def restore_state(self, symbol: str, lt: int, orders: [], tp=()):
        for order in orders:
            self.create_order(
                symbol=symbol,
                client_order_id='',
                buy=order['buy'],
                amount=any2str(order['amount']),
                price=any2str(order['price']),
                lt=lt,
                order_id=order['id']
            )

            if tp:
                funds = self.funds
                if order['buy']:
                    funds.base['free'] = str(Decimal(funds.base.get('free', 0)) - tp[0])
                    funds.quote['free'] = str(Decimal(funds.quote.get('free', 0)) + tp[1])
                else:
                    funds.base['free'] = str(Decimal(funds.base.get('free', 0)) + tp[0])
                    funds.quote['free'] = str(Decimal(funds.quote.get('free', 0)) - tp[1])
