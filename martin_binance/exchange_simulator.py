#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Free trading system for Binance SPOT API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.17b5"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from decimal import Decimal
import time

class Funds:
    def __init__(self, base=dict, quote=dict):
        self.base = base
        self.quote = quote

    def get(self):
        return [self.base, self.quote]


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
       self.workingTime = str(-1)
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


        return vars(order)


a = Account()

res = a.create_order(symbol="AAABBB",
                     client_order_id='123',
                     buy=True,
                     amount='0.001',
                     price='27500.00')

print(res)





