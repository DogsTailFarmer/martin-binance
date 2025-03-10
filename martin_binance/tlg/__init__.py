# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: telegram_proxy/tlg_proxy.proto
# plugin: python-betterproto
# This file has been @generated

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Dict,
    Optional,
)

import betterproto
import grpclib
from betterproto.grpc.grpclib_server import ServiceBase


if TYPE_CHECKING:
    import grpclib.server
    from betterproto.grpc.grpclib_client import MetadataLike
    from grpclib.metadata import Deadline


@dataclass(eq=False, repr=False)
class Request(betterproto.Message):
    bot_id: str = betterproto.string_field(1)
    token: str = betterproto.string_field(2)
    chat_id: str = betterproto.string_field(3)
    inline_buttons: bool = betterproto.bool_field(4)
    data: str = betterproto.string_field(5)


@dataclass(eq=False, repr=False)
class Response(betterproto.Message):
    bot_id: str = betterproto.string_field(1)
    data: str = betterproto.string_field(2)


class TlgProxyStub(betterproto.ServiceStub):
    async def post_message(
        self,
        request: "Request",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None
    ) -> "Response":
        return await self._unary_unary(
            "/tlg.TlgProxy/PostMessage",
            request,
            Response,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_update(
        self,
        request: "Request",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None
    ) -> "Response":
        return await self._unary_unary(
            "/tlg.TlgProxy/GetUpdate",
            request,
            Response,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )


class TlgProxyBase(ServiceBase):

    async def post_message(self, request: "Request") -> "Response":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_update(self, request: "Request") -> "Response":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def __rpc_post_message(
        self, stream: "grpclib.server.Stream[Request, Response]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.post_message(request)
        await stream.send_message(response)

    async def __rpc_get_update(
        self, stream: "grpclib.server.Stream[Request, Response]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_update(request)
        await stream.send_message(response)

    def __mapping__(self) -> Dict[str, grpclib.const.Handler]:
        return {
            "/tlg.TlgProxy/PostMessage": grpclib.const.Handler(
                self.__rpc_post_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                Request,
                Response,
            ),
            "/tlg.TlgProxy/GetUpdate": grpclib.const.Handler(
                self.__rpc_get_update,
                grpclib.const.Cardinality.UNARY_UNARY,
                Request,
                Response,
            ),
        }
