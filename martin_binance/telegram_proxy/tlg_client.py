#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram proxy client

"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2025 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.17rc8"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

# Generate ssl certificates
# cd ~/.MartinBinance/keys
# Proxy Service pair
# openssl req -x509 -newkey rsa:2048 -nodes -subj '/CN=localhost' --addext 'subjectAltName=IP:AAA.BBB.CCC.DDD'\
# -keyout tlg-proxy.key -out tlg-proxy.pem
#
# Client pair
# openssl req -x509 -newkey rsa:2048 -nodes -subj '/CN=localhost' -keyout tlg-client.key -out tlg-client.pem

import ssl
from pathlib import Path
import asyncio

import toml
import random
import logging.handlers

import martin_binance.tlg as tlg
from martin_binance import LOG_FILE_TLG, CONFIG_FILE, CERT_DIR

from exchanges_wrapper import Channel, exceptions

#
logger = logging.getLogger(__name__)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
fh = logging.handlers.RotatingFileHandler(LOG_FILE_TLG, maxBytes=1000000, backupCount=10)
fh.setFormatter(formatter)
fh.setLevel(logging.INFO)
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
sh.setLevel(logging.INFO)
#
root_logger = logging.getLogger()
root_logger.setLevel(min([fh.level, sh.level]))
root_logger.addHandler(fh)
root_logger.addHandler(sh)
#
config = toml.load(str(CONFIG_FILE))['Telegram']
TLG_PROXY_HOST = config['tlg_proxy_host']
TLG_PROXY_PORT = config['tlg_proxy_port']
SERVER_CERT = Path(CERT_DIR, "tlg-proxy.pem")
CLIENT_CERT = Path(CERT_DIR, "tlg-client.pem")
CLIENT_KEY = Path(CERT_DIR, "tlg-client.key")


def create_secure_context(client_cert: Path, client_key: Path, *, trusted: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(trusted))
    ctx.load_cert_chain(str(client_cert), str(client_key))
    ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
    ctx.set_alpn_protocols(['h2'])
    return ctx


SSL_CONTEXT = create_secure_context(CLIENT_CERT, CLIENT_KEY, trusted=SERVER_CERT)


class TlgClient:
    def __init__(self, bot_id, token, chat_id):
        self.bot_id = bot_id
        self.token = token
        self.chat_id = chat_id
        #
        self.channel = None
        self.stub = None
        self.init_event = asyncio.Event()
        self.init_event.set()
        #
        self.tasks = set()

    def tasks_manage(self, coro, name=None, add_done_callback=True):
        _t = asyncio.create_task(coro, name=name)
        self.tasks.add(_t)
        if add_done_callback:
            _t.add_done_callback(self.tasks.discard)

    def task_cancel(self):
        [task.cancel() for task in self.tasks if not task.done()]

    async def connect(self):
        self.init_event.clear()
        delay = 0
        while True:
            try:
                if self.channel:
                    self.channel.close()
                self.channel = Channel(TLG_PROXY_HOST, TLG_PROXY_PORT, ssl=SSL_CONTEXT)
                self.stub = tlg.TlgProxyStub(self.channel)
                await self.post_message("Connected", reraise=True)
                self.init_event.set()
                break
            except ConnectionRefusedError:
                delay += random.randint(1, 15)  # NOSONAR python:S2245
                logger.warning(f"Try connecting to Telegram proxy, retrying in {delay} second... ")
                await asyncio.sleep(delay)

    async def post_message(self, text, inline_buttons=False, reraise=False) -> tlg.Response:
        try:
            res = await self.stub.post_message(
                tlg.Request(
                    bot_id=self.bot_id,
                    token=self.token,
                    chat_id=self.chat_id,
                    inline_buttons=inline_buttons,
                    data=f"{self.bot_id}. {text}"
                )
            )
            return res
        except (ConnectionRefusedError, exceptions.StreamTerminatedError):
            logger.warning("Connection refused to Telegram proxy (post_message), waiting reconnection...")
            if self.init_event.is_set():
                self.tasks_manage(self.connect())
            elif reraise:
                raise
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass  # user interrupt

    async def get_update(self) -> tlg.Response:
        try:
            res = await self.stub.get_update(
                tlg.Request(
                    bot_id=self.bot_id,
                )
            )
            return res
        except (ConnectionRefusedError, exceptions.StreamTerminatedError):
            if self.init_event.is_set():
                self.tasks_manage(self.connect())
            logger.warning("Connection refused to Telegram proxy (get_update), waiting reconnection...")
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass  # user interrupt

    def close(self):
        self.channel.close()
        self.task_cancel()