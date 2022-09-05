#!/usr/bin/python3.8
# -*- coding: utf-8 -*-
"""
gRPC async client for exchanges-wrapper
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.6-14"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
# noinspection PyPackageRequirements
import grpc
import random
import logging

from exchanges_wrapper import api_pb2, api_pb2_grpc

logger = logging.getLogger('logger')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
# stream_handler.setLevel(logging.INFO)
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


class Client:
    def __init__(self, channel_options, account_name, rate_limiter):
        self.channel = grpc.aio.insecure_channel(target='localhost:50051', options=channel_options)
        self.stub = api_pb2_grpc.MartinStub(self.channel)
        self.account_name = account_name
        self.rate_limiter = rate_limiter
        self.client: api_pb2.OpenClientConnectionId = None
        self.wait_connection = False

    async def get_client(self):
        if not self.wait_connection:
            self.wait_connection = True
            client = None
            while client is None:
                client = await self.connect()
                self.wait_connection = False
            self.client = client

    async def connect(self):
        try:
            _client = await self.stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
                account_name=self.account_name,
                rate_limiter=self.rate_limiter))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            # noinspection PyUnresolvedReferences
            status_code = ex.code()
            # noinspection PyUnresolvedReferences
            logger.error(f"Exception on register client: {status_code.name}, {ex.details()}")
            if status_code == grpc.StatusCode.FAILED_PRECONDITION:
                raise SystemExit(1)
            else:
                logger.info('Restart gRPC client session')
                await asyncio.sleep(random.uniform(1, 5))
                return
        else:
            logger.info(f"gRPC session started for client_id: {_client.client_id}")
            return _client

    async def send_request(self, _request, _request_type, **kwargs):
        kwargs['client_id'] = self.client.client_id
        try:
            res = await _request(_request_type(**kwargs))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            # noinspection PyUnresolvedReferences
            status_code = ex.code()
            # noinspection PyUnresolvedReferences
            logger.error(f"Exception on send request: {status_code.name}, {ex.details()}")
            # noinspection PyUnresolvedReferences
            if status_code == grpc.StatusCode.UNAVAILABLE and ex.details() == 'failed to connect to all addresses':
                logger.error("Connection to gRPC server failed, try reconnect...")
                await self.get_client()
            else:
                raise
        else:
            logger.info(f"send_request.res: {res}")
            return res
