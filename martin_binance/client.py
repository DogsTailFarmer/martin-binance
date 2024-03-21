"""
gRPC async client for exchanges-wrapper
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.1rc3"
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
stream_handler.setLevel(logging.WARNING)
logger.addHandler(stream_handler)


class Trade:
    def __init__(self, account_name, rate_limiter, symbol):
        self.channel = Channel('127.0.0.1', 50051)
        self.stub = mr.MartinStub(self.channel)
        self.account_name = account_name
        self.rate_limiter = rate_limiter
        self.symbol = symbol
        self.client = None
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
            _client = await self.stub.open_client_connection(
                mr.OpenClientConnectionRequest(
                    trade_id=self.trade_id,
                    account_name=self.account_name,
                    rate_limiter=self.rate_limiter,
                    symbol=self.symbol
                )
            )
        except asyncio.CancelledError:
            pass  # Task cancellation should not be logged as an error.
        except ConnectionRefusedError as ex:
            logger.error(f"{ex}, reconnect...")
            await asyncio.sleep(random.randint(5, 30))
            raise UserWarning from ex
        except GRPCError as ex:
            status_code = ex.status
            logger.error(f"Exception on register client: {status_code.name}, {ex.message}")
            if status_code == Status.FAILED_PRECONDITION:
                raise SystemExit(1) from ex
            logger.warning('Restart gRPC client session')
            await asyncio.sleep(random.randint(5, 30))
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
            pass  # Task cancellation should not be logged as an error
        except grpclib.exceptions.StreamTerminatedError:
            raise UserWarning("Have not connection to gRPC server")
        except ConnectionRefusedError:
            raise UserWarning("Connection to gRPC server broken")
        except GRPCError as ex:
            status_code = ex.status
            if status_code == Status.UNAVAILABLE:
                self.client = None
                raise UserWarning(
                    "Connection to gRPC server failed, wait connection..."
                ) from ex
            logger.debug(f"Send request {_request}: {status_code.name}, {ex.message}")
            raise
        except Exception as ex:
            logger.error(f"Exception on send request {ex}")
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
            pass  # Task cancellation should not be logged as an error
        except grpclib.exceptions.StreamTerminatedError:
            logger.warning("WSS connection to gRPC server was terminated")
        except GRPCError as ex:
            status_code = ex.status
            logger.warning(f"Exception on WSS loop: {status_code.name}, {ex.message}")
            raise
