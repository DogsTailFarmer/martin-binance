#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple exchange simulator for backtest purpose
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.3.0b4"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from decimal import Decimal
import pandas as pd


class Funds:
    def __init__(self):
        # {'asset': 'BTC', 'free': '0.0', 'locked': '0.0'}
        self.base = {}
        self.quote = {}

    def get(self):
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
    def __init__(self):
        self.funds = Funds()
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')
        self.orders = []
        self.orders_buy = pd.Series()
        self.orders_sell = pd.Series()
        self.trade_id = 0
        self.ticker = {}
        self.grid_buy = {}
        self.grid_sell = {}

    def create_order(self, symbol: str, client_order_id: str, buy: bool, amount: str, price: str, lt: int) -> {}:
        order_id = len(self.orders)
        order = Order(symbol=symbol,
                      order_id=order_id,
                      client_order_id=client_order_id,
                      buy=buy,
                      amount=amount,
                      price=price,
                      lt=lt)
        self.orders.append(order)
        if buy:
            self.orders_buy.at[order_id] = Decimal(price)
        else:
            self.orders_sell.at[order_id] = Decimal(price)
        self.funds.on_order_created(buy=buy, amount=amount, price=price)
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

    def cancel_order(self, order_id: int):
        order = self.orders.pop(order_id)
        order.status = 'CANCELED'
        if order.side == 'BUY':
            self.orders_buy = self.orders_buy.drop(order_id)
        else:
            self.orders_sell = self.orders_sell.drop(order_id)
        self.orders.insert(order_id, order)
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

    def on_ticker_update(self, ticker: {}) -> [dict]:
        # print(f"on_ticker_update.ticker: {ticker['lastPrice']}")
        # print(f"BUY: {self.orders_buy}")
        # print(f"SELL: {self.orders_sell}")
        orders_id = []
        _i = self.orders_buy[self.orders_buy >= Decimal(ticker['lastPrice'])].index
        self.orders_buy = self.orders_buy.drop(_i.values)
        orders_id.extend(_i.values)
        _i = self.orders_sell[self.orders_sell <= Decimal(ticker['lastPrice'])].index
        self.orders_sell = self.orders_sell.drop(_i.values)
        orders_id.extend(_i.values)
        # Save data for analytics
        ts = ticker['closeTime']
        self.ticker[ts] = ticker['lastPrice']
        if self.orders_sell.values.size:
            self.grid_sell[ts] = self.orders_sell
        if self.orders_buy.values.size:
            self.grid_buy[ts] = self.orders_buy
        #
        orders_filled = []
        for order_id in orders_id:
            order = self.orders.pop(order_id)
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
            self.orders.insert(order_id, order)
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
