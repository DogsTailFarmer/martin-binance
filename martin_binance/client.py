"""
gRPC async client for exchanges-wrapper
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021-2025 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.36"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import asyncio
import random
import logging

# noinspection PyPackageRequirements
import grpclib.exceptions
import shortuuid

from exchanges_wrapper import martin as mr, Channel, Status, GRPCError

logger = logging.getLogger('logger.client')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class Trade:
    __slots__ = (
        'channel',
        'stub',
        'account_name',
        'rate_limiter',
        'symbol',
        'client',
        'wait_connection',
        'trade_id'
    )

    def __init__(self, account_name, rate_limiter, symbol):
        self.channel = None
        self.stub = None
        self.account_name = account_name
        self.rate_limiter = rate_limiter
        self.symbol = symbol
        self.client = None
        self.wait_connection = False
        self.trade_id = shortuuid.uuid()

    async def restart_session(self):
        await self.send_request(self.stub.client_restart, mr.MarketRequest, symbol=self.symbol)
        await self.get_client()

    async def get_client(self):
        if self.wait_connection:
            return False
        self.wait_connection = True
        client = None
        while client is None:
            if self.channel:
                self.channel.close()
            self.channel = Channel('127.0.0.1', 50051)
            self.stub = mr.MartinStub(self.channel)
            try:
                client = await self.connect()
            except UserWarning as ex:
                logger.warning(ex)
                client = None
                await asyncio.sleep(random.randint(5, 30))
            else:
                self.client = client
                self.wait_connection = False
                return True

    async def connect(self):
        try:
            _client = await self.stub.open_client_connection(
                mr.OpenClientConnectionRequest(
                    trade_id=self.trade_id,
                    account_name=self.account_name,
                    rate_limiter=self.rate_limiter,
                    symbol=self.symbol
                )
            )
        except ConnectionRefusedError as ex:
            raise UserWarning(f"{ex}, reconnect...") from None
        except GRPCError as ex:
            status_code = ex.status
            if status_code == Status.FAILED_PRECONDITION:
                raise SystemExit(1) from ex
            raise UserWarning(f"Exception on register client: {status_code.name}, {ex.message}")

        logger.info(f"gRPC session started for client_id: {_client.client_id}, trade_id: {self.trade_id}")
        return _client

    async def send_request(self, _request, _request_type, **kwargs):
        if not self.client:
            logger.warning("Send gRPC request failed, not active client session, restart")
            if not await self.get_client():
                raise UserWarning("Connection to gRPC server in progress...")
        kwargs['client_id'] = self.client.client_id
        kwargs['trade_id'] = self.trade_id
        try:
            res = await _request(_request_type(**kwargs))
        except grpclib.exceptions.StreamTerminatedError:
            self.client = None
            raise UserWarning("Have not connection to gRPC server")
        except ConnectionRefusedError:
            self.client = None
            raise UserWarning("Connection to gRPC server broken")
        except GRPCError as ex:
            status_code = ex.status
            logger.debug(f"Send request {_request}: {status_code.name}, {ex.message}")
            if status_code == Status.UNAVAILABLE:
                self.client = None
                raise UserWarning("Wait connection to gRPC server") from None
            raise
        except Exception as ex:
            logger.error(f"Exception on send request {ex}")
        else:
            return res

    async def for_request(self, _request, _request_type, **kwargs):
        if not self.client:
            raise UserWarning("Start gRPC request loop failed, not active client session")
        kwargs['client_id'] = self.client.client_id
        kwargs['trade_id'] = self.trade_id
        try:
            async for res in _request(_request_type(**kwargs)):
                yield res
        except grpclib.exceptions.StreamTerminatedError:
            pass  # handling in send_request()
        except GRPCError as ex:
            status_code = ex.status
            logger.warning(f"Exception on WSS loop: {status_code.name}, {ex.message}")
            raise
        except Exception as ex:
            logger.debug(f"for_request: {ex}")
