"""
Telegram bot
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2021 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "2.0.0"
__maintainer__ = "DanyaSWorlD"
__contact__ = "https://github.com/DanyaSWorlD"

import requests
import json
import sqlite3
import queue
from requests.adapters import HTTPAdapter, Retry


def telegram(queue_to_tlg, _bot_id, url, token, channel_id, db_file, stop_tlg, inline_bot):
    url += token
    method = f'{url}/sendMessage'
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[101, 111, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))

    def get_keyboard_markup():
        return json.dumps({
            "inline_keyboard": [
                [
                    {'text': 'status', 'callback_data': 'status_callback'},
                    {'text': 'stop', 'callback_data': 'stop_callback'},
                    {'text': 'end', 'callback_data': 'end_callback'},
                    {'text': 'restart', 'callback_data': 'restart_callback'},
                ]
            ]})

    def requests_post(_method, _data, session, inline_buttons=False):
        if inline_bot and inline_buttons:
            keyboard = get_keyboard_markup()
            _data['reply_markup'] = keyboard
        _res = None
        try:
            _res = session.post(_method, data=_data)
        except requests.exceptions.RetryError as _exc:
            print(f"Telegram: {_exc}")
        except Exception as _exc:
            print(f"Telegram: {_exc}")
        return _res

    def parse_query(update_inner):
        update_id = update_inner.get('update_id')
        query = update_inner.get('callback_query')
        from_id = query.get('from').get('id')
        if from_id != int(channel_id):
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
        requests_post(
            f'{url}/answerCallbackQuery',
            {'callback_query_id': query.get('id')},
            s,
        )
        return {
            'update_id': update_id,
            'message_id': message_id,
            'text_in': command,
            'reply_to_message': reply_to_message
        }

    def parse_command(update_inner):
        update_id = update_inner.get('update_id')
        message = update_inner.get('message')
        from_id = message.get('from').get('id')
        if from_id != int(channel_id):
            return None
        message_id = message.get('message_id')
        text_in = update_inner.get('message').get('text')
        try:
            reply_to_message = message.get('reply_to_message').get('text')
        except AttributeError:
            reply_to_message = None
            _text = "The command must be a response to any message from a specific strategy," \
                    " use Reply + Menu combination"
            requests_post(method, _data={'chat_id': channel_id, 'text': _text}, session=s)
        return {
            'update_id': update_id,
            'message_id': message_id,
            'text_in': text_in,
            'reply_to_message': reply_to_message
        }

    def telegram_get(offset=None) -> []:
        command_list = []
        _method = f'{url}/getUpdates'
        _res = requests_post(_method, _data={'chat_id': channel_id, 'offset': offset}, session=s)
        if not _res or _res.status_code != 200:
            return command_list
        __result = _res.json().get('result')
        for result_in in __result:
            parsed = None
            if result_in.get('message') is not None:
                parsed = parse_command(result_in)
            if result_in.get('callback_query') is not None:
                parsed = parse_query(result_in)
            if parsed:
                command_list.append(parsed)
        return command_list

    def process_update(update_inner, offset=None):
        reply = update_inner.get('reply_to_message')
        if not reply:
            return
        in_bot_id = reply.split('.')[0]
        if in_bot_id != _bot_id:
            return
        try:
            msg_in = str(update_inner['text_in']).lower().strip().replace('/', '')
            if offset and msg_in == 'restart':
                telegram_get(offset_id)
            connection_control.execute('insert into t_control values(?,?,?,?)',
                                       (update_inner['message_id'], msg_in, in_bot_id, None))
            connection_control.commit()
        except sqlite3.Error as ex:
            print(f"telegram: insert into t_control: {ex}")
        else:
            # Send receipt
            post_text = f"Received '{msg_in}' command, OK"
            requests_post(method, _data={'chat_id': channel_id, 'text': post_text}, session=s)

    # Set command for Telegram bot
    _command = requests_post(f'{url}/getMyCommands', _data=None, session=s)
    if _command and _command.status_code == 200 and (not _command.json().get('result') or
                                                     len(_command.json().get('result')) < 4):
        _commands = {
            "commands": json.dumps([
                {"command": "status",
                 "description": "Get strategy status"},
                {"command": "stop",
                 "description": "Stop strategy after end of cycle, not for Reverse"},
                {"command": "end",
                 "description": "Stop strategy after executed TP order, in Direct and Reverse, all the same"},
                {"command": "restart",
                 "description": "Restart current pair with recovery"}
            ])
        }
        res = requests_post(f'{url}/setMyCommands', _data=_commands, session=s)
        print(f"Set or update command menu for Telegram bot: code: {res.status_code}, result: {res.json()}, "
              f"restart Telegram bot by /start command for update it")

    connection_control = sqlite3.connect(db_file)
    offset_id = None
    while True:
        try:
            text = queue_to_tlg.get(block=True, timeout=10)
        except KeyboardInterrupt:
            break
        except queue.Empty:
            # Get external command from Telegram bot
            updates = telegram_get(offset_id)
            if not updates:
                continue
            offset_id = updates[-1].get('update_id') + 1
            for update in updates:
                process_update(update, offset_id)
        else:
            if text and stop_tlg in text:
                connection_control.close()
                break
            requests_post(method, _data={'chat_id': channel_id, 'text': text}, session=s, inline_buttons=True)
