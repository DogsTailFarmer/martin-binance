#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
Binance API Server for Python3 binance API wrapper
margin.de <-> Python strategy <-> mPw <-> BinanceAPIServer <-> Python3 binance API wrapper <-> Binance API
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.0rc6"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import time
import weakref
# from pympler import tracker
import gc

import asyncio
import functools
import json
# import logging
import logging.handlers
import os
import sys
# from datetime import datetime

# noinspection PyPackageRequirements
import grpc
import toml
# noinspection PyPackageRequirements
from google.protobuf import json_format

# noinspection PyPackageRequirements
import binance  # lgtm [py/import-and-import-from]
import binance_api_pb2
import binance_api_pb2_grpc
# noinspection PyPackageRequirements
from binance import events

sys.tracebacklimit = 0
FILE_CONFIG = 'binance_srv_cfg.toml'
CONFIG = None
if os.path.exists(FILE_CONFIG):
    CONFIG = toml.load(FILE_CONFIG)
else:
    print("Can't find config file!")
    # noinspection PyProtectedMember, PyUnresolvedReferences
    os._exit(1)
HEARTBEAT = 1  # Sec


def get_account(_account_name: str) -> ():
    accounts = CONFIG.get('accounts')
    for account in accounts:
        if account.get('name') == _account_name:
            if account.get('test_net'):
                real_market = False
                api = CONFIG.get('endpoint_test').get('api')
                ws = CONFIG.get('endpoint_test').get('ws')
            else:
                real_market = True
                api = CONFIG.get('endpoint').get('api')
                ws = CONFIG.get('endpoint').get('ws')
            return account.get('api_key'), account.get('api_secret'), api, ws, real_market
    return ()


class OpenClient:
    open_clients = []

    def __init__(self, _account_name: str):
        api_key, api_secret, api, ws, real_mrkt = get_account(_account_name)  # lgtm [py/mismatched-multiple-assignment]
        self.name = _account_name
        self.real_market = real_mrkt
        self.client = binance.Client(api_key, api_secret, endpoint=api)
        self.endpoint_ws = ws
        self.stop_streams_for_symbol = None
        self.on_order_update_queue = asyncio.Queue()
        OpenClient.open_clients.append(self)

    @classmethod
    def get_id(cls, _account_name):
        _id = 0
        for open_client in cls.open_clients:
            if open_client.name == _account_name:
                _id = id(open_client)
                break
        return _id

    @classmethod
    def get_client(cls, _id):
        _client = None
        for open_client in cls.open_clients:
            if id(open_client) == _id:
                _client = open_client
                break
        return _client


class Event:
    def __init__(self, event_data: {}):
        self.symbol = event_data["symbol"]
        self.client_order_id = event_data["clientOrderId"]
        self.side = event_data["side"]
        self.order_type = event_data["type"]
        self.time_in_force = event_data["timeInForce"]
        self.order_quantity = event_data["origQty"]
        self.order_price = event_data["price"]
        self.stop_price = event_data["stopPrice"]
        self.iceberg_quantity = event_data["icebergQty"]
        self.order_list_id = event_data["orderListId"]
        self.original_client_id = event_data["clientOrderId"]
        self.execution_type = "TRADE"
        self.order_status = event_data["status"]
        self.order_reject_reason = "NONE"
        self.order_id = event_data["orderId"]
        self.last_executed_quantity = event_data["executedQty"]
        self.cumulative_filled_quantity = event_data["executedQty"]
        self.last_executed_price = event_data["price"]
        self.commission_amount = "0.0"
        self.commission_asset = ""
        self.transaction_time = event_data["updateTime"]
        self.trade_id = 1
        self.ignore_a = int()
        self.in_order_book = False
        self.is_maker_side = False
        self.ignore_b = False
        self.order_creation_time = event_data["time"]
        self.quote_asset_transacted = event_data["cummulativeQuoteQty"]
        self.last_quote_asset_transacted = event_data["cummulativeQuoteQty"]
        self.quote_order_quantity = event_data["origQuoteOrderQty"]


# noinspection PyPep8Naming,PyMethodMayBeStatic,PyUnusedLocal
class Martin(binance_api_pb2_grpc.MartinServicer):
    rate_limit_reached_time = None
    rate_limiter = None

    async def OpenClientConnection(self, request: binance_api_pb2.OpenClientConnectionRequest,
                                   context: grpc.aio.ServicerContext) -> binance_api_pb2.OpenClientConnectionId:
        # logger.info(f"OpenClientConnection: {request.account_name}")
        client_id = OpenClient.get_id(request.account_name)
        if not client_id and get_account(request.account_name):
            open_client = OpenClient(request.account_name)
            if open_client:
                await open_client.client.load()
                client_id = id(open_client)
        # Set rate_limiter
        Martin.rate_limiter = max(Martin.rate_limiter if Martin.rate_limiter else 0, request.rate_limiter)
        return binance_api_pb2.OpenClientConnectionId(client_id=client_id, srv_version=__version__)

    async def FetchServerTime(self, request: binance_api_pb2.OpenClientConnectionId,
                              context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchServerTimeResponse:
        client = OpenClient.get_client(request.client_id).client
        res = await client.fetch_server_time()
        server_time = res.get('serverTime')
        return binance_api_pb2.FetchServerTimeResponse(server_time=server_time)

    async def ResetRateLimit(self, request: binance_api_pb2.OpenClientConnectionId,
                             context: grpc.aio.ServicerContext) -> binance_api_pb2.SimpleResponse:
        Martin.rate_limiter = max(Martin.rate_limiter if Martin.rate_limiter else 0, request.rate_limiter)
        _success = False
        if Martin.rate_limit_reached_time:
            if time.time() - Martin.rate_limit_reached_time > 60:
                OpenClient.get_client(request.client_id).client.http.rate_limit_reached = False
                Martin.rate_limit_reached_time = None
                logger.info("ResetRateLimit error clear, trying one else time")
                _success = True
        else:
            if OpenClient.get_client(request.client_id).client.http.rate_limit_reached:
                Martin.rate_limit_reached_time = time.time()
        return binance_api_pb2.SimpleResponse(success=_success)

    async def FetchOpenOrders(self, request: binance_api_pb2.MarketRequest,
                              context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchOpenOrdersResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        # message list
        response = binance_api_pb2.FetchOpenOrdersResponse()
        # Nested dict
        response_order = binance_api_pb2.FetchOpenOrdersResponse.Order()
        try:
            res = await client.fetch_open_orders(symbol=request.symbol, receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.info(f"FetchOpenOrders for {open_client.name}:{request.symbol} exception: {_ex}")
            if 'Rate limit reached' in str(_ex):
                Martin.rate_limit_reached_time = time.time()
            raise
        else:
            # logger.info(f"FetchOpenOrders: {res}")
            for order in res:
                new_order = json_format.ParseDict(order, response_order)
                response.items.append(new_order)
        response.rate_limiter = Martin.rate_limiter
        return response

    async def FetchOrder(self, request: binance_api_pb2.FetchOrderRequest,
                         context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchOrderResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = open_client.on_order_update_queue
        response = binance_api_pb2.FetchOrderResponse()
        try:
            res = await client.fetch_order(symbol=request.symbol,
                                           order_id=request.order_id,
                                           origin_client_order_id=None,
                                           receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.info(f"FetchOrders for {open_client.name}:{request.symbol} exception: {_ex}")
        else:
            # logger.info(f"FetchOrder: {res}")
            if request.filled_update_call and res.get('status') == 'FILLED':
                # logger.info(f"FetchOrder: {res.get('status')}")
                event = Event(res)
                logger.info(f"FetchOrder.event: {open_client.name}:{event.symbol}:{int(event.order_id)}:"
                            f"{event.order_status}")
                _event = weakref.ref(event)
                await _queue.put(_event())
            json_format.ParseDict(res, response)
        return response

    async def CancelAllOrders(self, request: binance_api_pb2.MarketRequest,
                              context: grpc.aio.ServicerContext) -> binance_api_pb2.CancelAllOrdersResponse:
        client = OpenClient.get_client(request.client_id).client
        # message list
        response = binance_api_pb2.CancelAllOrdersResponse()
        # Nested dict
        response_order = binance_api_pb2.CancelAllOrdersResponse.CancelOrder()
        res = await client.cancel_all_orders(symbol=request.symbol, receive_window=None)
        # logger.info(f"CancelAllOrders: {res}")
        for order in res:
            cancel_order = json_format.ParseDict(order, response_order)
            response.items.append(cancel_order)
        return response

    async def FetchExchangeInfoSymbol(self, request: binance_api_pb2.MarketRequest,
                                      context: grpc.aio.ServicerContext
                                      ) -> binance_api_pb2.FetchExchangeInfoSymbolResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.FetchExchangeInfoSymbolResponse()
        exchange_info = await client.fetch_exchange_info()
        exchange_info_symbol = {}
        try:
            exchange_info_symbol = next(item for item in exchange_info.get('symbols')
                                        if item["symbol"] == request.symbol)
        except StopIteration:
            logger.info("FetchExchangeInfoSymbol.exchange_info_symbol: None")
        # logger.info(f"exchange_info_symbol: {exchange_info_symbol}")
        filters_res = exchange_info_symbol.pop('filters', [])
        json_format.ParseDict(exchange_info_symbol, response)
        # logger.info(f"filters: {filters_res}")
        filters = response.filters
        for _filter in filters_res:
            if _filter.get('filterType') == 'PRICE_FILTER':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.PriceFilter()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.price_filter.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'PERCENT_PRICE':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.PercentPrice()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.percent_price.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'LOT_SIZE':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.LotSize()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.lot_size.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'MIN_NOTIONAL':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.MinNotional()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.min_notional.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'ICEBERG_PARTS':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.IcebergParts()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.iceberg_parts.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'MARKET_LOT_SIZE':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.MarketLotSize()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.market_lot_size.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'MAX_NUM_ORDERS':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumOrders()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.max_num_orders.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'MAX_NUM_ICEBERG_ORDERS':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxNumIcebergOrders()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.max_num_iceberg_orders.CopyFrom(new_filter)
            elif _filter.get('filterType') == 'MAX_POSITION':
                new_filter_template = binance_api_pb2.FetchExchangeInfoSymbolResponse.Filters.MaxPosition()
                new_filter = json_format.ParseDict(_filter, new_filter_template)
                filters.max_position.CopyFrom(new_filter)
        return response

    async def FetchAccountInformation(self, request: binance_api_pb2.OpenClientConnectionId,
                                      context: grpc.aio.ServicerContext
                                      ) -> binance_api_pb2.FetchAccountBalanceResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = binance_api_pb2.FetchAccountBalanceResponse()
        response_balance = binance_api_pb2.FetchAccountBalanceResponse.Balances()
        account_information = await client.fetch_account_information(receive_window=None)
        # logger.info(f"account_information: {account_information}")
        # Send only balances
        res = account_information.get('balances', [])
        # Create consolidated list of asset balances from SPOT and Funding wallets
        balances = []
        for i in res:
            _free = float(i.get('free'))
            _locked = float(i.get('locked'))
            if _free or _locked:
                balances.append({'asset': i.get('asset'), 'free': i.get('free'), 'locked': i.get('locked')})
        # logger.info(f"account_information.balances: {balances}")
        for balance in balances:
            new_balance = json_format.ParseDict(balance, response_balance)
            response.balances.extend([new_balance])
        return response

    async def FetchFundingWallet(self, request: binance_api_pb2.FetchFundingWalletRequest,
                                 context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchFundingWalletResponse:
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        response = binance_api_pb2.FetchFundingWalletResponse()
        response_balance = binance_api_pb2.FetchFundingWalletResponse.Balances()
        res = []
        if open_client.real_market:
            try:
                res = await client.fetch_funding_wallet(asset=request.asset,
                                                        need_btc_valuation=request.need_btc_valuation,
                                                        receive_window=request.receive_window)
            except AttributeError:
                logger.error("Can't get Funding Wallet balances, try update binance.py to the last version")
        # logger.info(f"funding_wallet: {res}")
        for balance in res:
            new_balance = json_format.ParseDict(balance, response_balance)
            response.balances.extend([new_balance])
        return response

    async def FetchOrderBook(self, request: binance_api_pb2.MarketRequest,
                             context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchOrderBookResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.FetchOrderBookResponse()
        res = await client.fetch_order_book(symbol=request.symbol, limit=5)
        res_bids = res.get('bids', [])
        res_asks = res.get('asks', [])
        response.lastUpdateId = res.get('lastUpdateId')
        for bid in res_bids:
            response.bids.append(json.dumps(bid))
        for ask in res_asks:
            response.asks.append(json.dumps(ask))
        return response

    async def FetchSymbolPriceTicker(
            self, request: binance_api_pb2.MarketRequest,
            context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchSymbolPriceTickerResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.FetchSymbolPriceTickerResponse()
        res = await client.fetch_symbol_price_ticker(symbol=request.symbol)
        json_format.ParseDict(res, response)
        return response

    async def FetchTickerPriceChangeStatistics(
            self, request: binance_api_pb2.MarketRequest,
            context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchTickerPriceChangeStatisticsResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.FetchTickerPriceChangeStatisticsResponse()
        res = await client.fetch_ticker_price_change_statistics(symbol=request.symbol)
        json_format.ParseDict(res, response)
        return response

    async def FetchKlines(self, request: binance_api_pb2.FetchKlinesRequest,
                          context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchKlinesResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.FetchKlinesResponse()
        try:
            res = await client.fetch_klines(symbol=request.symbol, interval=request.interval,
                                            start_time=None, end_time=None, limit=request.limit)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.info(f"FetchKlines for {request.symbol} interval: {request.interval}, exception: {_ex}")
        else:
            # logger.info(res)
            for candle in res:
                response.klines.append(json.dumps(candle))
        return response

    async def OnKlinesUpdate(self, request: binance_api_pb2.FetchKlinesRequest,
                             context: grpc.aio.ServicerContext) -> binance_api_pb2.OnKlinesUpdateResponse:
        response = binance_api_pb2.OnKlinesUpdateResponse()
        _queue = asyncio.Queue()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        open_client.stop_streams_for_symbol = str()
        # logger.info(f"OnKlinesUpdate.events_1: {client.events.registered_streams}")
        # logger.info(f"OnKlinesUpdate.events_2: {client.events.handlers}")
        client.events.register_event(functools.partial(on_klines_update, _queue),
                                     request.symbol.lower() + "@kline_" + request.interval)
        # logger.info(f"OnKlinesUpdate.events_3: {client.events.registered_streams}")
        # logger.info(f"OnKlinesUpdate.events_4: {client.events.handlers}")
        # Restart stream
        loop.create_task(open_client.client.start_market_events_listener())
        while True:
            if open_client.stop_streams_for_symbol == request.symbol:
                logger.info(f"OnKlinesUpdate: Stop market stream for {open_client.name}:{request.symbol}:"
                            f"{request.interval}")
                return
            _event = await _queue.get()
            # logger.info(f"OnKlinesUpdate.event: {_event.symbol}:{_event.kline_interval}")
            response.symbol = _event.symbol
            response.interval = _event.kline_interval
            candle = [_event.kline_start_time,
                      _event.kline_open_price,
                      _event.kline_high_price,
                      _event.kline_low_price,
                      _event.kline_close_price,
                      _event.kline_base_asset_volume,
                      _event.kline_close_time,
                      _event.kline_quote_asset_volume,
                      _event.kline_trades_number,
                      _event.kline_taker_buy_base_asset_volume,
                      _event.kline_taker_buy_quote_asset_volume,
                      _event.kline_ignore
                      ]
            response.candle = json.dumps(candle)
            yield response

    async def FetchAccountTradeList(self, request: binance_api_pb2.AccountTradeListRequest,
                                    context: grpc.aio.ServicerContext) -> binance_api_pb2.AccountTradeListResponse:
        client = OpenClient.get_client(request.client_id).client
        response = binance_api_pb2.AccountTradeListResponse()
        response_trade = binance_api_pb2.AccountTradeListResponse.Trade()
        res = await client.fetch_account_trade_list(
            symbol=request.symbol,
            start_time=None,
            end_time=None,
            from_id=None,
            limit=request.limit,
            receive_window=None)
        # logger.info(f"FetchAccountTradeList: {res}")
        for trade in res:
            trade_order = json_format.ParseDict(trade, response_trade)
            response.items.append(trade_order)
        return response

    async def OnTickerUpdate(self, request: binance_api_pb2.MarketRequest,
                             context: grpc.aio.ServicerContext) -> binance_api_pb2.OnTickerUpdateResponse:
        response = binance_api_pb2.OnTickerUpdateResponse()
        _queue = asyncio.Queue()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        open_client.stop_streams_for_symbol = str()
        # logger.info(f"OnTickerUpdate.events_1: {client.events.registered_streams}")
        # logger.info(f"OnTickerUpdate.events_2: {client.events.handlers}")
        client.events.register_event(functools.partial(on_ticker_update, _queue),
                                     request.symbol.lower() + "@miniTicker")
        # logger.info(f"OnTickerUpdate.events_3: {client.events.registered_streams}")
        # logger.info(f"OnTickerUpdate.events_4: {client.events.handlers}")
        # Restart stream
        loop.create_task(open_client.client.start_market_events_listener())
        while True:
            if open_client.stop_streams_for_symbol == request.symbol:
                logger.info(f"OnTickerUpdate: Stop market stream for {open_client.name}: {request.symbol}")
                return
            _event = await _queue.get()
            # logger.info(f"OnTickerUpdate.event: {_event.symbol}")
            ticker_24h = {'symbol': _event.symbol,
                          'open_price': _event.open_price,
                          'close_price': _event.close_price,
                          'event_time': _event.event_time}
            json_format.ParseDict(ticker_24h, response)
            yield response

    async def OnOrderBookUpdate(self, request: binance_api_pb2.MarketRequest,
                                context: grpc.aio.ServicerContext) -> binance_api_pb2.FetchOrderBookResponse:
        response = binance_api_pb2.FetchOrderBookResponse()
        _queue = asyncio.Queue()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        open_client.stop_streams_for_symbol = str()
        client.events.register_event(functools.partial(on_order_book_update, _queue), request.symbol.lower()+"@depth5")
        loop.create_task(open_client.client.start_market_events_listener())
        while True:
            if open_client.stop_streams_for_symbol == request.symbol:
                logger.info(f"OnOrderBookUpdate: Stop market stream for {open_client.name}: {request.symbol}")
                return
            _event = await _queue.get()
            # logger.info(f"OnOrderBookUpdate._event: {_event}")
            response.Clear()
            response.lastUpdateId = _event.last_update_id
            for bid in _event.bids:
                response.bids.append(json.dumps(bid))
            for ask in _event.asks:
                response.asks.append(json.dumps(ask))
            yield response

    async def OnFundsUpdate(self, request: binance_api_pb2.OnFundsUpdateRequest,
                            context: grpc.aio.ServicerContext) -> binance_api_pb2.OnFundsUpdateResponse:
        response = binance_api_pb2.OnFundsUpdateResponse()
        _queue = asyncio.Queue()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        open_client.stop_streams_for_symbol = str()
        client.events.register_user_event(functools.partial(on_funds_update, _queue), 'outboundAccountPosition')
        loop.create_task(client.start_user_events_listener(endpoint=open_client.endpoint_ws))
        while True:
            if open_client.stop_streams_for_symbol == request.symbol:
                logger.info(f"OnFundsUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            _event = await _queue.get()
            # logger.info(f"OnFundsUpdate: {_event.balances.keys()}")
            response.funds = json.dumps(_event.balances)
            yield response

    async def OnOrderUpdate(self, request: binance_api_pb2.MarketRequest,
                            context: grpc.aio.ServicerContext) -> binance_api_pb2.OnOrderUpdateResponse:
        response = binance_api_pb2.OnOrderUpdateResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        _queue = open_client.on_order_update_queue
        open_client.stop_streams_for_symbol = str()
        client.events.register_user_event(functools.partial(on_order_update, _queue), 'executionReport')
        loop.create_task(client.start_user_events_listener(endpoint=open_client.endpoint_ws))
        while True:
            if open_client.stop_streams_for_symbol == request.symbol:
                logger.info(f"OnOrderUpdate: Stop user stream for {open_client.name}: {request.symbol}")
                return
            _event = await _queue.get()
            # logger.info(f"OnOrderUpdate._event: {int(_event.order_id)}, {_event.order_status}")
            response.symbol = _event.symbol
            response.client_order_id = _event.client_order_id
            response.side = _event.side
            response.order_type = _event.order_type
            response.time_in_force = _event.time_in_force
            response.order_quantity = _event.order_quantity
            response.order_price = _event.order_price
            response.stop_price = _event.stop_price
            response.iceberg_quantity = _event.iceberg_quantity
            response.order_list_id = int(_event.order_list_id)
            response.original_client_id = _event.original_client_id
            response.execution_type = _event.execution_type
            response.order_status = _event.order_status
            response.order_reject_reason = _event.order_reject_reason
            response.order_id = int(_event.order_id)
            response.last_executed_quantity = _event.last_executed_quantity
            response.cumulative_filled_quantity = _event.cumulative_filled_quantity
            response.last_executed_price = _event.last_executed_price
            response.commission_amount = _event.commission_amount
            response.commission_asset = _event.commission_asset if _event.commission_asset else ''
            response.transaction_time = int(_event.transaction_time)
            response.trade_id = int(_event.trade_id)
            response.ignore_a = _event.ignore_a
            response.in_order_book = _event.in_order_book
            response.is_maker_side = bool(_event.is_maker_side)
            response.ignore_b = _event.ignore_b
            response.order_creation_time = int(_event.order_creation_time)
            response.quote_asset_transacted = _event.quote_asset_transacted
            response.last_quote_asset_transacted = _event.last_quote_asset_transacted
            response.quote_order_quantity = _event.quote_order_quantity
            yield response

    async def CreateLimitOrder(self, request: binance_api_pb2.CreateLimitOrderRequest,
                               context: grpc.aio.ServicerContext) -> binance_api_pb2.CreateLimitOrderResponse:
        response = binance_api_pb2.CreateLimitOrderResponse()
        client = OpenClient.get_client(request.client_id).client
        # logger.info(f"CreateLimitOrder: quantity: {request.quantity}, price: {request.price}")
        res = await client.create_order(
            request.symbol,
            binance.Side.BUY if request.buy_side else binance.Side.SELL,
            order_type=binance.OrderType.LIMIT,
            time_in_force=binance.TimeInForce.GTC,
            quantity=request.quantity,
            quote_order_quantity=None,
            price=request.price,
            new_client_order_id=request.new_client_order_id,
            stop_price=None,
            iceberg_quantity=None,
            response_type=binance.ResponseType.RESULT.value,
            receive_window=None,
            test=False)
        json_format.ParseDict(res, response)
        return response

    async def CancelOrder(self, request: binance_api_pb2.CancelOrderRequest,
                          context: grpc.aio.ServicerContext) -> binance_api_pb2.CancelOrderResponse:
        response = binance_api_pb2.CancelOrderResponse()
        open_client = OpenClient.get_client(request.client_id)
        client = open_client.client
        try:
            res = await client.cancel_order(
                request.symbol,
                order_id=request.order_id,
                origin_client_order_id=None,
                new_client_order_id=None,
                receive_window=None)
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error
        except Exception as _ex:
            logger.info(f"CancelOrder for {open_client.name}:{request.symbol} exception: {_ex}")
            if 'Rate limit reached' in str(_ex):
                Martin.rate_limit_reached_time = time.time()
            raise
        else:
            json_format.ParseDict(res, response)
        return response

    async def StopStream(self, request: binance_api_pb2.MarketRequest,
                         context: grpc.aio.ServicerContext) -> binance_api_pb2.SimpleResponse:
        # logger.info(f"StopStream")
        open_client = OpenClient.get_client(request.client_id)
        response = binance_api_pb2.SimpleResponse()
        open_client.stop_streams_for_symbol = request.symbol
        await asyncio.sleep(HEARTBEAT)
        await open_client.client.stop_market_events_listener()
        # logger.info(f"StopStream.events_1: {open_client.client.events.registered_streams}")
        # logger.info(f"StopStream.events_2: {open_client.client.events.handlers}")
        # Unregister event
        _registered_streams = open_client.client.events.registered_streams.copy()
        for _i in _registered_streams:
            if request.symbol.lower() in _i:
                # logger.info(f"StopStream remove: {_i}")
                open_client.client.events.unregister(None, _i)
        # logger.info(f"StopStream.events_3: {open_client.client.events.registered_streams}")
        # logger.info(f"StopStream.events_4: {open_client.client.events.handlers}")
        gc.collect(generation=2)
        response.success = True
        return response


async def on_klines_update(_queue, event: events.KlineWrapper):
    # logger.info(f"on_klines_update.event: {event}")
    _event = weakref.ref(event)
    await _queue.put(_event())


async def on_order_update(_queue, event: events.OrderUpdateWrapper):
    # logger.info(f"on_order_book_update.event: {event}")
    _event = weakref.ref(event)
    await _queue.put(_event())


async def on_funds_update(_queue, event: events.SymbolMiniTickerWrapper):
    # logger.info(f"on_funds_update.event: {event}")
    _event = weakref.ref(event)
    await _queue.put(_event())


async def on_ticker_update(_queue, event: events.SymbolMiniTickerWrapper):
    # logger.info(f"on_ticker_update.event: {event.event_type}, {event.event_time}")
    _event = weakref.ref(event)
    await _queue.put(_event())


async def on_order_book_update(_queue, event: events.PartialBookDepthWrapper):
    # logger.info(f"on_order_book_update.event: {event.lastUpdateId}")
    _event = weakref.ref(event)
    await _queue.put(_event())


async def serve() -> None:
    server = grpc.aio.server()
    binance_api_pb2_grpc.add_MartinServicer_to_server(Martin(), server)
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    logger.info(f"Starting server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()


if __name__ == '__main__':
    FILE_LOG = f"{CONFIG.get('Path').get('log_path')}binance_srv.log"
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
    fh = logging.handlers.RotatingFileHandler(FILE_LOG, maxBytes=1000000, backupCount=10)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    #
    loop = asyncio.get_event_loop()
    loop.create_task(serve())
    loop.run_forever()
    loop.close()
