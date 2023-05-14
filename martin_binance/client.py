"""
gRPC async client for exchanges-wrapper
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "1.2.17b1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
# noinspection PyPackageRequirements
import grpc
import random
import logging
import uuid

from exchanges_wrapper import api_pb2, api_pb2_grpc

logger = logging.getLogger('logger.client')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
# stream_handler.setLevel(logging.INFO)
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


class Trade:
    def __init__(self, channel_options, account_name, rate_limiter):
        self.channel = grpc.aio.insecure_channel(target='localhost:50051', options=channel_options)
        self.stub = api_pb2_grpc.MartinStub(self.channel)
        self.account_name = account_name
        self.rate_limiter = rate_limiter
        self.client: api_pb2.OpenClientConnectionId = None
        self.wait_connection = False
        self.trade_id = str(uuid.uuid4().hex)

    async def get_client(self):
        if not self.wait_connection:
            self.wait_connection = True
            client = None
            while client is None:
                try:
                    client = await self.connect()
                except UserWarning:
                    client = None
                else:
                    self.wait_connection = False
                    self.client = client

    async def connect(self):
        try:
            _client = await self.stub.OpenClientConnection(api_pb2.OpenClientConnectionRequest(
                trade_id=self.trade_id,
                account_name=self.account_name,
                rate_limiter=self.rate_limiter))
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except grpc.RpcError as ex:
            status_code = ex.code()
            logger.error(f"Exception on register client: {status_code.name}, {ex.details()}")
            if status_code == grpc.StatusCode.FAILED_PRECONDITION:
                raise SystemExit(1)
            logger.info('Restart gRPC client session')
            await asyncio.sleep(random.randint(5, 15))
            raise UserWarning
        else:
            logger.info(f"gRPC session started for client_id: {_client.client_id}\n"
                        f"trade_id: {self.trade_id}")
            return _client

    async def send_request(self, _request, _request_type, **kwargs):
        if self.client:
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
                    raise UserWarning("Connection to gRPC server failed, wait connection...")
                if status_code == grpc.StatusCode.RESOURCE_EXHAUSTED:
                    raise
                logger.error(f"Exception on send request {_request}: {status_code.name}, {ex.details()}")
                raise
            else:
                # logger.info(f"send_request.res: {res}")
                return res
        else:
            raise UserWarning("Send gRPC request failed, not active client session")

    async def for_request(self, _request, _request_type, **kwargs):
        if self.client:
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
        else:
            raise UserWarning("Start gRPC request loop failed, not active client session")
