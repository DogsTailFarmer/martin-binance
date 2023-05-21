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
import time


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
    def __init__(self, symbol: str, order_id: str, client_order_id: str, buy: bool, amount: str, price: str):
       self.symbol = symbol
       self.orderId = order_id
       self.orderListId = -1
       self.clientOrderId = client_order_id
       self.transactTime = str(int(time.time() * 1000))
       self.price = price
       self.origQty = amount
       self.executedQty = '0.00000000'
       self.cummulativeQuoteQty = '0.00000000'
       self.status = 'NEW'
       self.timeInForce = 'GTC'
       self.type = 'LIMIT'
       self.side = "BUY" if buy else "SELL"
       self.workingTime = "-1"
       self.selfTradePreventionMode = 'NONE'


class Account:
    def __init__(self):
        self.funds = Funds()
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')
        self.orders = []

    def create_order(self, symbol: str, client_order_id: str, buy: bool, amount: str, price: str) -> {}:
        order = Order(symbol=symbol,
                      order_id=str(len(self.orders)),
                      client_order_id=client_order_id,
                      buy=buy,
                      amount=amount,
                      price=price)
        self.orders.append(order)
        self.funds.on_order_created(buy=buy, amount=amount, price=price)
        return {'symbol': order.symbol,
                'orderId': order.orderId,
                'orderListId': order.orderListId,
                'clientOrderId': order.clientOrderId,
                'transactTime': order.transactTime,
                'price': order.price,
                'origQty': order.origQty,
                'executedQty': order.executedQty,
                'cummulativeQuoteQty': order.cummulativeQuoteQty,
                'status': order.status,
                'timeInForce': order.timeInForce,
                'type': order.type,
                'side': order.side,
                'workingTime': order.workingTime,
                'selfTradePreventionMode': order.selfTradePreventionMode}

    def cancel_order(self, order_id: int):
        order = self.orders.pop(order_id)
        order.status = 'CANCELED'
        self.orders.insert(order_id, order)
        self.funds.on_order_canceled(order.side, order.origQty, order.price)
        return {'symbol': order.symbol,
                'origClientOrderId': order.clientOrderId,
                'orderId': order.orderId,
                'orderListId': order.orderListId,
                'clientOrderId': 'qwert',
                'price': order.price,
                'origQty': order.origQty,
                'executedQty': order.executedQty,
                'cummulativeQuoteQty': order.cummulativeQuoteQty,
                'status': order.status,
                'timeInForce': order.timeInForce,
                'type': order.type,
                'side': order.side,
                'selfTradePreventionMode': order.selfTradePreventionMode}

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