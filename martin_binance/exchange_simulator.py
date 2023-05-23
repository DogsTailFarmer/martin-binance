#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple exchange simulator for backtest purpose
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.17b6"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from decimal import Decimal


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

class Order:
    def __init__(self, symbol: str, order_id: str, client_order_id: str, buy: bool, amount: str, price: str, lt: int):
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
        self.order_creation_time: lt
        self.quote_asset_transacted: str
        self.last_quote_asset_transacted: str
        self.quote_order_quantity: str


class Account:
    def __init__(self):
        self.funds = Funds()
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')
        self.orders = []
        self.trade_id = 0

    def create_order(self, symbol: str, client_order_id: str, buy: bool, amount: str, price: str, lt: int) -> {}:
        order = Order(symbol=symbol,
                      order_id=str(len(self.orders)),
                      client_order_id=client_order_id,
                      buy=buy,
                      amount=amount,
                      price=price,
                      lt=lt)
        self.orders.append(order)
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
        print(f"on_ticker_update.ticker: {ticker}")

        filled_orders = []


        return [{'event_time': 1684786472546,
                'symbol': 'BTCUSDT',
                'client_order_id': '2014001',
                'side': 'SELL',
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'order_quantity': '0.00125800',
                'order_price': '26859.42000000',
                'stop_price': '0.00000000',
                'iceberg_quantity': '0.00000000',
                'order_list_id': -1,
                'original_client_id': '',
                'execution_type': 'TRADE',
                'order_status': 'FILLED',
                'order_reject_reason': 'NONE',
                'order_id': 8544417,
                'last_executed_quantity': '0.00125800',
                'cumulative_filled_quantity': '0.00125800',
                'last_executed_price': '26859.42000000',
                'commission_amount': '0.00000000',
                'commission_asset': 'USDT',
                'transaction_time': 1684786472546,
                'trade_id': 2772544,
                'ignore_a': 19865672,
                'in_order_book': False,
                'is_maker_side': True,
                'ignore_b': True,
                'order_creation_time': 1684786471821,
                'quote_asset_transacted': '33.78915036',
                'last_quote_asset_transacted': '33.78915036',
                'quote_order_quantity': '0.00000000'}
                ]


'''
a = Account()

a.funds.base = {'asset': 'AAA', 'free': '1.0', 'locked': '0.0'}
a.funds.quote = {'asset': 'BBB', 'free': '100.0', 'locked': '0.0'}

res = a.create_order(symbol="AAABBB",
                     client_order_id='123',
                     buy=True,
                     amount='0.001',
                     price='27500.00')

print(res)

print(a.funds.get())
'''