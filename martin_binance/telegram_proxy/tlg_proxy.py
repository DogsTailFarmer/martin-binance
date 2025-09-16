#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script sets up a Telegram proxy server with secure SSL context.
It configures logging, loads configuration from a TOML file, and establishes
retry policies for HTTP requests. The script also defines a function to create
a secure context for SSL connections and provides a method to generate keyboard
markup for Telegram bot commands.
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2025 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.0.36"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import ssl
from pathlib import Path
import socket
import asyncio
import logging.handlers
import requests
import toml
from requests.adapters import HTTPAdapter, Retry
import ujson as json

import martin_binance.tlg as tlg
from martin_binance import LOG_FILE_TLG, CONFIG_FILE, CERT_DIR
from martin_binance.lib import tasks_manage
from exchanges_wrapper import Server, graceful_exit
#
logger = logging.getLogger('tlg_proxy')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s")
#
fh = logging.handlers.RotatingFileHandler(LOG_FILE_TLG, maxBytes=1000000, backupCount=10)
fh.setFormatter(formatter)
logger.addHandler(fh)
fh.setLevel(logging.DEBUG)
#
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)
sh.setLevel(logging.INFO)
#
CLIENT_CERT = Path(CERT_DIR, "tlg-client.pem")
SERVER_CERT = Path(CERT_DIR, "tlg-proxy.pem")
SERVER_KEY = Path(CERT_DIR, "tlg-proxy.key")

config = toml.load(str(CONFIG_FILE))['Telegram']
TLG_URL = config['tlg_url']
TLG_PROXY_HOST = config['tlg_proxy_host']
TLG_PROXY_PORT = config['tlg_proxy_port']
HEARTBEAT = config['heartbeat']

SESSION = requests.Session()
retries = Retry(total=50, backoff_factor=1, status_forcelist=[101, 104, 111, 502, 503, 504])
SESSION.mount('https://', HTTPAdapter(max_retries=retries))
COMMAND_COUNT = 5


def create_secure_context(server_cert: Path, server_key: Path, *, trusted: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH,
        cafile=str(trusted),
    )
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_cert_chain(str(server_cert), str(server_key))
    ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
    ctx.set_alpn_protocols(['h2'])
    return ctx


def get_keyboard_markup():
    return json.dumps({
        "inline_keyboard": [
            [
                {'text': 'status', 'callback_data': 'status_callback'},
                {'text': 'stop', 'callback_data': 'stop_callback'},
                {'text': 'end', 'callback_data': 'end_callback'},
                {'text': 'restart', 'callback_data': 'restart_callback'},
                {'text': 'exit', 'callback_data': 'exit_callback'},
            ]
        ]})


def requests_post(_method, _data, inline_buttons=False):
    if inline_buttons:
        keyboard = get_keyboard_markup()
        _data['reply_markup'] = keyboard
    _res = None
    try:
        _res = SESSION.post(_method, data=_data)
    except requests.exceptions.RetryError as _exc:
        logger.error(f"Telegram: {_exc}")
    except Exception as _exc:
        logger.error(f"Telegram: {_exc}")
    return _res


def parse_command(token, chat_id, update_inner):
    update_id = update_inner.get('update_id')
    message = update_inner.get('message')
    from_id = message.get('from').get('id')
    if from_id != int(chat_id):
        return None
    message_id = message.get('message_id')
    text_in = update_inner.get('message').get('text')
    try:
        reply_to_message = message.get('reply_to_message').get('text')
    except AttributeError:
        reply_to_message = None
        _text = "The command must be a response to any message from a specific strategy," \
                " use Reply + Menu combination"
        requests_post(f'{TLG_URL}{token}/sendMessage', _data={'chat_id': chat_id, 'text': _text})
    return {
        'update_id': update_id,
        'message_id': message_id,
        'text_in': text_in,
        'reply_to_message': reply_to_message
    }


def parse_query(token, chat_id, update_inner):
    update_id = update_inner.get('update_id')
    query = update_inner.get('callback_query')
    from_id = query.get('from').get('id')
    if from_id != int(chat_id):
        return None
    message = query.get('message')
    message_id = message.get('message_id')
    query_data = query.get('data')
    reply_to_message = message.get('text')
    command = None
    if query_data == 'status_callback':
        command = 'status'
    elif query_data == 'stop_callback':
        command = 'stop'
    elif query_data == 'end_callback':
        command = 'end'
    elif query_data == 'restart_callback':
        command = 'restart'
    elif query_data == 'exit_callback':
        command = 'exit'
    requests_post(
        f'{TLG_URL}{token}//answerCallbackQuery',
        {'callback_query_id': query.get('id')}
    )
    return {
        'update_id': update_id,
        'message_id': message_id,
        'text_in': command,
        'reply_to_message': reply_to_message
    }


def telegram_get(token, chat_id, offset=None) -> list:
    command_list = []
    _method = f'{TLG_URL}{token}/getUpdates'
    _res = requests_post(_method, _data={'chat_id': chat_id, 'offset': offset})
    if not _res or _res.status_code != 200:
        if _res and _res.status_code != 200:
            logger.error(_res)
        return command_list
    __result = _res.json().get('result')
    for result_in in __result:
        parsed = None
        if result_in.get('message') is not None:
            parsed = parse_command(token, chat_id, result_in)
        if result_in.get('callback_query') is not None:
            parsed = parse_query(token, chat_id, result_in)
        if parsed:
            command_list.append(parsed)
    return command_list


def process_update(token, chat_id, update_inner):
    logger.debug(f"process_update.update_inner: {update_inner}")
    reply = update_inner.get('reply_to_message')
    if not reply:
        return
    in_bot_id = reply.split('.')[0]
    if in_bot_id not in TlgProxy.bot_ids:
        return
    msg_in = str(update_inner['text_in']).lower().strip().replace('/', '')
    TlgProxy.command[in_bot_id] = msg_in
    post_text = f"{in_bot_id}. received '{msg_in}' command, ran to do"
    requests_post(
        f'{TLG_URL}{token}/sendMessage',
        _data={'chat_id': chat_id, 'text': post_text}
    )


def set_bot_commands(token):
    # Set command for Telegram bot
    _command = requests_post(f'{TLG_URL}{token}/getMyCommands', _data=None)
    if _command and _command.status_code == 200 and (not _command.json().get('result') or
                                                     len(_command.json().get('result')) < COMMAND_COUNT):
        _commands = {
            "commands": json.dumps([
                {"command": "status",
                 "description": "Get strategy status"},
                {"command": "stop",
                 "description": "Stop strategy after end of cycle, not for Reverse"},
                {"command": "end",
                 "description": "Stop strategy after executed TP order, in Direct and Reverse, all the same"},
                {"command": "restart",
                 "description": "Restart current pair with recovery"},
                {"command": "exit",
                 "description": "Exit from apps as Ctrl-C locally"}
            ])
        }
        res = requests_post(f'{TLG_URL}{token}/setMyCommands', _data=_commands)
        logger.info(f"Set or update command menu for Telegram bot: code: {res.status_code}, result: {res.json()},"
                    f" restart Telegram bot by /start command for update it")


async def poll_update(request: tlg.Request):
    offset_id = None
    logger.info(f"New bot started, on request: {request.bot_id}")
    while True:
        await asyncio.sleep(HEARTBEAT)
        # Get external command from Telegram bot
        updates = telegram_get(request.token, request.chat_id, offset_id)
        if not updates:
            continue
        offset_id = updates[-1].get('update_id') + 1
        for update in updates:
            process_update(request.token, request.chat_id, update)


class TlgProxy(tlg.TlgProxyBase):
    bot_tokens = set()
    bot_ids = set()
    tasks = set()
    command = {}

    async def post_message(self, request: tlg.Request) -> tlg.Response:
        TlgProxy.bot_ids.add(request.bot_id)
        if request.token not in self.bot_tokens:
            TlgProxy.bot_tokens.add(request.token)
            set_bot_commands(request.token)
            # Start polling task
            tasks_manage(self.tasks, poll_update(request), name='poll_update')
        # Post message
        res = requests_post(
            f'{TLG_URL}{request.token}/sendMessage',
            _data={'chat_id': request.chat_id, 'text': request.data},
            inline_buttons=request.inline_buttons
        )
        return tlg.Response(bot_id=request.bot_id, data=json.dumps(res.status_code if res else None))

    async def get_update(self, request: tlg.Request):
        return tlg.Response(bot_id=request.bot_id, data=json.dumps(TlgProxy.command.pop(request.bot_id, None)))


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


async def main(host=TLG_PROXY_HOST, port=TLG_PROXY_PORT):
    if is_port_in_use(host, port):
        raise SystemExit(f"gRPC Telegram proxy: local port {port} already used")

    server = Server([TlgProxy()])
    with graceful_exit([server]):
        await server.start(
            host,
            port,
            ssl=create_secure_context(SERVER_CERT, SERVER_KEY, trusted=CLIENT_CERT)
        )
        logger.info(f"Starting Telegram proxy service on {host}:{port}")
        await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
