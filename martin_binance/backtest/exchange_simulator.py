#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple exchange simulator for backtest purpose
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.1rc3"
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
        base = self.base.copy()
        base |= {'free': str(base['free']), 'locked': str(base['locked'])}
        quote = self.quote.copy()
        quote |= {'free': str(quote['free']), 'locked': str(quote['locked'])}
        return [base, quote]

    def on_order_created(self, buy: bool, amount: Decimal, price: Decimal):
        if buy:
            self.quote['free'] -= amount * price
            self.quote['locked'] += amount * price
        else:
            self.base['free'] -= amount
            self.base['locked'] += amount

    def on_order_canceled(self, side: str, amount: Decimal, price: Decimal):
        if side == 'BUY':
            self.quote['free'] += amount * price
            self.quote['locked'] -= amount * price
        else:
            self.base['free'] += amount
            self.base['locked'] -= amount

    def on_order_filled(self, side: str, amount: Decimal, price: Decimal, fee: Decimal):
        if side == 'BUY':
            self.base['free'] += amount - fee * amount / 100
            self.quote['locked'] -= amount * price
        else:
            self.base['locked'] -= amount
            self.quote['free'] += amount * price - fee * (amount * price) / 100


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
        self.price = Decimal(price)
        self.orig_qty = Decimal(amount)
        self.executed_qty = Decimal('0')
        self.cummulative_quote_qty = Decimal('0')
        self.status = 'NEW'
        self.time_in_force = 'GTC'
        self.type = 'LIMIT'
        self.side = "BUY" if buy else "SELL"
        self.working_time = "-1"
        self.self_trade_prevention_mode = 'NONE'
        #
        self.event_time: int
        self.last_executed_quantity = Decimal('0')
        self.cumulative_filled_quantity = Decimal('0')
        self.last_executed_price = Decimal('0')
        self.trade_id: int
        self.order_creation_time = lt
        self.quote_asset_transacted = Decimal('0')
        self.last_quote_asset_transacted = Decimal('0')
        self.quote_order_quantity = self.orig_qty * self.price


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
        order = Order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            buy=buy,
            amount=amount,
            price=price,
            lt=lt
        )

        if buy:
            self.orders_buy.at[order_id] = Decimal(price)
            if self.save_ds:
                self.grid_buy[lt] = self.orders_buy
        else:
            self.orders_sell.at[order_id] = Decimal(price)
            if self.save_ds:
                self.grid_sell[lt] = self.orders_sell
            #
        self.funds.on_order_created(buy=buy, amount=Decimal(amount), price=Decimal(price))
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
                    'price': str(order.price),
                    'origQty': str(order.orig_qty),
                    'executedQty': str(order.executed_qty),
                    'cummulativeQuoteQty': str(order.cummulative_quote_qty),
                    'status': order.status,
                    'timeInForce': order.time_in_force,
                    'type': order.type,
                    'side': order.side,
                    'selfTradePreventionMode': order.self_trade_prevention_mode}

    def on_ticker_update(self, ticker: {}, ts: int) -> [dict]:
        # print(f"on_ticker_update.ticker: {ts}: {ticker}")
        # print(f"BUY: {self.orders_buy}")
        # print(f"SELL: {self.orders_sell}")

        filled_buy_id = []
        filled_sell_id = []
        orders_id = []
        orders_filled = []

        self.ticker_last = Decimal(ticker['lastPrice'])
        qty = Decimal(ticker['Qty'])
        part = bool(qty)

        if self.market_ids:
            orders_id.extend(self.market_ids)

        orders_id.extend(self.orders_buy[self.orders_buy >= self.ticker_last].index.values)
        orders_id.extend(self.orders_sell[self.orders_sell <= self.ticker_last].index.values)

        if self.save_ds:
            # Save data for analytics
            self.ticker[ts] = ticker['lastPrice']
            if self.orders_sell.values.size:
                self.grid_sell[ts] = self.orders_sell
            if self.orders_buy.values.size:
                self.grid_buy[ts] = self.orders_buy
        #
        for order_id in orders_id:
            if part and not qty:
                break

            order = self.orders.get(order_id)

            order.transact_time = int(ticker['closeTime'])
            order.event_time = order.transact_time
            order.trade_id = self.trade_id = self.trade_id + 1

            order.last_executed_price = self.ticker_last

            delta = order.orig_qty - order.executed_qty
            order.last_executed_quantity = last_executed_qty = min(delta, qty) if part else delta
            order.executed_qty += last_executed_qty
            order.last_quote_asset_transacted = order.last_executed_price * last_executed_qty
            order.quote_asset_transacted += order.last_quote_asset_transacted

            if part:
                qty -= last_executed_qty

            order.cumulative_filled_quantity = order.executed_qty
            order.cummulative_quote_qty = order.quote_asset_transacted

            if order.executed_qty >= order.orig_qty:
                order.status = 'FILLED'
                if order.side == 'BUY':
                    filled_buy_id.append(order_id)
                else:
                    filled_sell_id.append(order_id)
            elif 0 < order.executed_qty < order.orig_qty:
                order.status = 'PARTIALLY_FILLED'
            #
            self.orders[order_id] = order
            #
            res = {
                'event_time': order.event_time,
                'symbol': order.symbol,
                'client_order_id': order.client_order_id,
                'side': order.side,
                'order_type': order.type,
                'time_in_force': order.time_in_force,
                'order_quantity': str(order.orig_qty),
                'order_price': str(order.price),
                'stop_price': '0',
                'iceberg_quantity': '0',
                'order_list_id': -1,
                'original_client_id': order.client_order_id,
                'execution_type': 'TRADE',
                'order_status': order.status,
                'order_reject_reason': 'NONE',
                'order_id': order_id,
                'last_executed_quantity': str(order.last_executed_quantity),
                'cumulative_filled_quantity': str(order.cumulative_filled_quantity),
                'last_executed_price': str(order.last_executed_price),
                'commission_amount': '0',
                'commission_asset': '',
                'transaction_time': order.transact_time,
                'trade_id': order.trade_id,
                'ignore_a': 12345678,
                'in_order_book': False,
                'is_maker_side': False if order_id in self.market_ids else True,
                'ignore_b': True,
                'order_creation_time': order.order_creation_time,
                'quote_asset_transacted': str(order.quote_asset_transacted),
                'last_quote_asset_transacted': str(order.last_quote_asset_transacted),
                'quote_order_quantity': str(order.quote_order_quantity)
            }
            #
            orders_filled.append(res)
            self.funds.on_order_filled(
                order.side,
                order.last_executed_quantity,
                order.last_executed_price,
                self.fee_taker if order_id in self.market_ids else self.fee_maker
            )
            #
        self.orders_buy = self.orders_buy.drop(filled_buy_id)
        self.orders_sell = self.orders_sell.drop(filled_sell_id)
        self.market_ids.clear()

        return orders_filled

    def restore_state(self, symbol: str, lt: int, orders: [], sum_amount: ()):
        if sum_amount[0]:
            self.funds.base['free'] += sum_amount[1]
            self.funds.quote['free'] -= sum_amount[2]
        else:
            self.funds.base['free'] -= sum_amount[1]
            self.funds.quote['free'] += sum_amount[2]

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
