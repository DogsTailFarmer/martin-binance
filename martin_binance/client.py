"""
gRPC async client for exchanges-wrapper
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.2.0.b10"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
# noinspection PyPackageRequirements
import grpc
import random
import logging
import shortuuid

from exchanges_wrapper import api_pb2, api_pb2_grpc

logger = logging.getLogger('logger.client')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
stream_handler.setLevel(logging.WARNING)
logger.addHandler(stream_handler)


class Trade:
    def __init__(self, channel_options, account_name, rate_limiter, symbol):
        self.channel = grpc.aio.insecure_channel(target='localhost:50051', options=channel_options)
        self.stub = api_pb2_grpc.MartinStub(self.channel)
        self.account_name = account_name
        self.rate_limiter = rate_limiter
        self.symbol = symbol
        self.client: api_pb2.OpenClientConnectionId = None
        self.wait_connection = False
        self.trade_id = shortuuid.uuid()

    async def get_client(self):
        if self.wait_connection:
            return False
        self.wait_connection = True
        client = None
        while client is None:
            try:
                client = await self.connect()
            except UserWarning:
                client = None
            else:
                self.client = client
                self.wait_connection = False
                return True

    async def connect(self):
        try:
            _client = await self.stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
                trade_id=self.trade_id,
                account_name=self.account_name,
                rate_limiter=self.rate_limiter,
                symbol=self.symbol
            ))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            status_code = ex.code()
            logger.error(f"Exception on register client: {status_code.name}, {ex.details()}")
            if status_code == grpc.StatusCode.FAILED_PRECONDITION:
                raise SystemExit(1) from ex
            logger.warning('Restart gRPC client session')
            await asyncio.sleep(random.randint(5, 15))
            raise UserWarning from ex
        else:
            logger.info(f"gRPC session started for client_id: {_client.client_id}\n"
                        f"trade_id: {self.trade_id}")
            return _client

    async def send_request(self, _request, _request_type, **kwargs):
        if not self.client:
            raise UserWarning("Send gRPC request failed, not active client session")
        kwargs['client_id'] = self.client.client_id
        kwargs['trade_id'] = self.trade_id
        try:
            res = await _request(_request_type(**kwargs))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            status_code = ex.code()
            if (
                (status_code == grpc.StatusCode.UNAVAILABLE
                 and 'failed to connect to all addresses' in (ex.details()))
                    or
                (status_code == grpc.StatusCode.UNKNOWN
                 and "'NoneType' object has no attribute 'client'" in ex.details())
            ):
                self.client = None
                raise UserWarning(
                    "Connection to gRPC server failed, wait connection..."
                ) from ex
            if status_code == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise
            logger.debug(f"Exception on send request {_request}: {status_code.name}, {ex.details()}")
            raise
        else:
            if res is None:
                self.client = None
                asyncio.create_task(self.get_client())
                raise UserWarning("Can't get response, restart connection to gRPC server ...")
            return res

    async def for_request(self, _request, _request_type, **kwargs):
        if not self.client:
            raise UserWarning("Start gRPC request loop failed, not active client session")
        kwargs['client_id'] = self.client.client_id
        kwargs['trade_id'] = self.trade_id
        try:
            async for res in _request(_request_type(**kwargs)):
                yield res
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            status_code = ex.code()
            logger.warning(f"Exception on WSS loop: {status_code.name}, {ex.details()}")
            raise
