#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple exchange simulator for backtest purpose
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.2.1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

from decimal import Decimal
from typing import Dict

from martin_binance.lib import Orders


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

    def on_order_filled(self, side: str, amount: Decimal, price: Decimal, last_price: Decimal, fee: Decimal):
        if side == 'BUY':
            self.base['free'] += amount - fee * amount / 100
            self.quote['locked'] -= amount * price
            self.quote['free'] += amount * (price - last_price)
        else:
            self.base['locked'] -= amount
            self.quote['free'] += amount * last_price - fee * (amount * last_price) / 100


# =====================================================================
# 1. СЛУЖЕБНЫЙ КЛАСС ОРДЕРА ДЛЯ СИМУЛЯТОРА (Имя изменено на SimOrder)
# =====================================================================
class SimOrder:
    __slots__ = (
        "symbol", "id", "order_list_id", "client_order_id", "timestamp",
        "price", "amount", "received_amount", "cummulative_quote_qty", "status",
        "time_in_force", "order_type", "side", "working_time", "self_trade_prevention_mode",
        "event_time", "last_executed_quantity", "cumulative_filled_quantity",
        "last_executed_price", "trade_id", "order_creation_time", "quote_asset_transacted",
        "last_quote_asset_transacted", "quote_order_quantity",
    )

    def __init__(self, symbol: str, order_id: int, client_order_id: str, buy: bool, amount: str, price: str, lt: int):
        self.symbol = symbol
        self.id = order_id
        self.order_list_id = -1
        self.client_order_id = client_order_id
        self.timestamp = lt  # local time
        self.price = Decimal(price)
        self.amount = Decimal(amount)
        self.received_amount = Decimal('0')
        self.cummulative_quote_qty = Decimal('0')
        self.status = 'NEW'
        self.time_in_force = 'GTC'
        self.order_type = 'LIMIT'
        self.side = "BUY" if buy else "SELL"
        self.working_time = "-1"
        self.self_trade_prevention_mode = 'NONE'
        # Service variables for simulation execution
        self.last_executed_quantity = Decimal('0')
        self.cumulative_filled_quantity = Decimal('0')
        self.last_executed_price = Decimal('0')
        self.order_creation_time = lt
        self.quote_asset_transacted = Decimal('0')
        self.last_quote_asset_transacted = Decimal('0')
        self.quote_order_quantity = self.amount * self.price


# =====================================================================
# 2. МОДИФИЦИРОВАННЫЙ КЛАСС АККАУНТА (ACCOUNT)
# =====================================================================
class Account:
    __slots__ = (
        "save_ds", "funds", "fee_maker", "fee_taker", "orders",
        "orders_buy", "orders_sell", "trade_id", "ticker",
        "grid_buy", "grid_sell", "ticker_last", "market_ids",
    )

    def __init__(self, save_ds: bool):
        self.save_ds = save_ds
        self.funds = Funds()
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')

        # Интеграция: Переводим хранилище симулятора на ваш класс Orders
        self.orders: Orders = Orders()

        # Оптимизация: Переводим активные сетки на быстрые плоские словари Python {id: price}
        self.orders_buy: Dict[int, Decimal] = {}
        self.orders_sell: Dict[int, Decimal] = {}

        self.trade_id = 0
        self.ticker = {}

        # Вложенные словари {ts: {id: price}} для аналитики
        self.grid_buy: Dict[int, dict] = {}
        self.grid_sell: Dict[int, dict] = {}

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
            order_id=None) -> dict:

        if order_id is None:
            # Используем ваш новый штатный метод получения списка ID
            existing_ids = self.orders.get_id_list()
            order_id = max(existing_ids) + 1 if existing_ids else 1

        order = SimOrder(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            buy=buy,
            amount=amount,
            price=price,
            lt=lt
        )

        dec_price = Decimal(price)

        if buy:
            self.orders_buy[order_id] = dec_price
            if self.save_ds:
                self.grid_buy[lt] = dict(self.orders_buy)
        else:
            self.orders_sell[order_id] = dec_price
            if self.save_ds:
                self.grid_sell[lt] = dict(self.orders_sell)

        self.funds.on_order_created(buy=buy, amount=Decimal(amount), price=dec_price)

        # Интеграция: используем метод update вашего класса Orders для сохранения SimOrder
        self.orders.update(order)

        if self.ticker_last and ((buy and dec_price >= self.ticker_last) or
                                 (not buy and dec_price <= self.ticker_last)):
            self.market_ids.append(order_id)

        return {'symbol': order.symbol,
                'orderId': order.id,
                'orderListId': order.order_list_id,
                'clientOrderId': order.client_order_id,
                'transactTime': order.timestamp,
                'price': order.price,
                'origQty': order.amount,
                'executedQty': order.received_amount,
                'cummulativeQuoteQty': order.cummulative_quote_qty,
                'status': order.status,
                'timeInForce': order.time_in_force,
                'type': order.order_type,
                'side': order.side,
                'workingTime': order.working_time,
                'selfTradePreventionMode': order.self_trade_prevention_mode}

    def cancel_order(self, order_id: int, ts: int) -> dict:
        # Получаем SimOrder из нашего нового класса Orders
        order: SimOrder = self.orders.get_by_id(order_id)
        if order is None:
            raise UserWarning(f"Error on Cancel order, can't find {order_id} anymore")

        order.status = 'CANCELED'

        # Оптимизированное удаление из текущих активных сеток симулятора
        if order.side == 'BUY':
            if order_id in self.orders_buy:
                del self.orders_buy[order_id]
                if self.save_ds and self.orders_buy:
                    self.grid_buy[ts] = dict(self.orders_buy)
        else:
            if order_id in self.orders_sell:
                del self.orders_sell[order_id]
                if self.save_ds and self.orders_sell:
                    self.grid_sell[ts] = dict(self.orders_sell)

        # Вызываем методы баланса фонда
        self.funds.on_order_canceled(order.side, order.amount - order.received_amount, order.price)

        # Удаляем ордер из пула активных ордеров симулятора
        self.orders.remove(order_id)

        # СОВМЕСТИМОСТЬ: Возвращаем оригинальный сырой словарь отмены
        return {'symbol': order.symbol,
                'origClientOrderId': order.client_order_id,
                'orderId': order.id,
                'orderListId': order.order_list_id,
                'clientOrderId': 'qwert',
                'price': str(order.price),
                'origQty': str(order.amount),
                'executedQty': str(order.received_amount),
                'cummulativeQuoteQty': str(order.cummulative_quote_qty),
                'status': order.status,
                'timeInForce': order.time_in_force,
                'type': order.order_type,
                'side': order.side,
                'selfTradePreventionMode': order.self_trade_prevention_mode}

    def on_ticker_update(self, ticker: dict, ts: int) -> list[dict]:
        filled_buy_id = []
        filled_sell_id = []
        orders_id = []
        orders_filled = []

        self.ticker_last = Decimal(ticker['lastPrice'])
        qty = Decimal(ticker['Qty'])
        part = bool(qty)

        if self.market_ids:
            orders_id.extend(self.market_ids)

        # ОПТИМИЗАЦИЯ: Сверхбыстрый Си-поиск по словарям вместо тяжелого Pandas Series
        # Находим ID ордеров, чья цена удовлетворяет условиям исполнения
        orders_id.extend([oid for oid, price in self.orders_buy.items() if price >= self.ticker_last])
        orders_id.extend([oid for oid, price in self.orders_sell.items() if price <= self.ticker_last])

        if self.save_ds:
            # Сохраняем слепки истории в виде чистых словарей
            self.ticker[ts] = ticker['lastPrice']
            if self.orders_sell:
                self.grid_sell[ts] = dict(self.orders_sell)
            if self.orders_buy:
                self.grid_buy[ts] = dict(self.orders_buy)

        for order_id in orders_id:
            if part and not qty:
                break

            # ИНТЕГРАЦИЯ: Достаем SimOrder из нашего приватного словаря класса Orders
            order: SimOrder = self.orders.get_by_id(order_id)
            if not order:
                continue

            order.timestamp = int(ticker['closeTime'])
            order.event_time = order.timestamp
            self.trade_id += 1
            order.trade_id = self.trade_id

            order.last_executed_price = self.ticker_last

            delta = order.amount - order.received_amount
            order.last_executed_quantity = last_executed_qty = min(delta, qty) if part else delta
            order.received_amount += last_executed_qty
            order.last_quote_asset_transacted = order.last_executed_price * last_executed_qty
            order.quote_asset_transacted += order.last_quote_asset_transacted

            if part:
                qty -= last_executed_qty

            order.cumulative_filled_quantity = order.received_amount
            order.cummulative_quote_qty = order.quote_asset_transacted

            # Проверяем финальный статус исполнения ордера
            if order.received_amount >= order.amount:
                order.status = 'FILLED'
                if order.side == 'BUY':
                    filled_buy_id.append(order_id)
                else:
                    filled_sell_id.append(order_id)
            elif 0 < order.received_amount < order.amount:
                order.status = 'PARTIALLY_FILLED'

            # СОВМЕСТИМОСТЬ: Генерируем оригинальную структуру WS-ответа Binance
            res = {
                'event_time': order.event_time,
                'symbol': order.symbol,
                'client_order_id': order.client_order_id,
                'side': order.side,
                'order_type': order.order_type,
                'time_in_force': order.time_in_force,
                'order_quantity': str(order.amount),
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
                'transaction_time': order.timestamp,
                'trade_id': order.trade_id,
                'ignore_a': 12345678,
                'in_order_book': False,
                'is_maker_side': bool(order_id not in self.market_ids),
                'ignore_b': True,
                'order_creation_time': order.order_creation_time,
                'quote_asset_transacted': str(order.quote_asset_transacted),
                'last_quote_asset_transacted': str(order.last_quote_asset_transacted),
                'quote_order_quantity': str(order.quote_order_quantity)
            }

            orders_filled.append(res)

            self.funds.on_order_filled(
                order.side,
                order.last_executed_quantity,
                order.price,
                order.last_executed_price,
                self.fee_taker if order_id in self.market_ids else self.fee_maker
            )

        # ОПТИМИЗАЦИЯ: Чистим активные сетки словарей встроенным del вместо .drop()
        for bid in filled_buy_id:
            self.orders_buy.pop(bid, None)
            self.orders.remove(bid)  # Сразу вычищаем исполненные ордера из нашего Orders

        for sid in filled_sell_id:
            self.orders_sell.pop(sid, None)
            self.orders.remove(sid)  # Сразу вычищаем исполненные ордера из нашего Orders

        self.market_ids.clear()

        return orders_filled

    def restore_state(self, symbol: str, lt: int, orders_manager: Orders, sum_amount: tuple):
        """
        Restores simulator state from the strategy's Orders object.
        Converts lightweight strategy 'Order' objects into simulation 'SimOrder'
        objects since partial fills are not used.
        """
        # 1. Восстанавливаем балансы фондов
        if sum_amount[0]:
            self.funds.base['free'] += sum_amount[1]
            self.funds.quote['free'] -= sum_amount[2]
        else:
            self.funds.base['free'] -= sum_amount[1]
            self.funds.quote['free'] += sum_amount[2]

        # 2. Очищаем старые ордера и тиковые сетки симулятора
        self.orders.clear()
        self.orders_buy.clear()
        self.orders_sell.clear()

        # 3. Быстрый перенос ордеров без логики частичного исполнения
        # orders_manager.get() возвращает внутренний словарь {id: Order}
        for order_id, strategy_order in orders_manager.get().items():

            # Создаем чистый технический SimOrder для бэктеста
            sim_order = SimOrder(
                symbol=symbol,
                order_id=order_id,
                client_order_id='',
                buy=strategy_order.buy,
                amount=str(strategy_order.amount),
                price=str(strategy_order.price),
                lt=lt
            )

            # Переносим базовые служебные атрибуты
            sim_order.order_type = strategy_order.order_type
            sim_order.timestamp = strategy_order.timestamp
            sim_order.order_creation_time = strategy_order.timestamp

            # Интегрируем SimOrder в пул симулятора
            self.orders.update(sim_order)

            # Заполняем быстрые словари матчинга тиков {id: price}
            if sim_order.side == "BUY":
                self.orders_buy[order_id] = sim_order.price
            else:
                self.orders_sell[order_id] = sim_order.price

        # 4. Сохраняем исторический слепок для аналитики (если включено)
        if self.save_ds:
            if self.orders_buy:
                self.grid_buy[lt] = dict(self.orders_buy)
            if self.orders_sell:
                self.grid_sell[lt] = dict(self.orders_sell)
