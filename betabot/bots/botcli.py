import logging
import mock
import os
import sys
import time
from urllib.parse import urlencode

import asyncio

from betabot.bots.bot import Bot
from betabot.channel import Channel
from betabot.chat import Chat

LOG = logging.getLogger(__name__)
log_level = logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
LOG.setLevel(log_level)

class BotCLI(Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.input_line = None
        self._user_id = 'U123'
        self._user_name = 'betabot'
        self._token = ''
        self._cli_channel = Channel(self, {'id': 'CLI'})

    async def _setup(self):
        asyncio.ensure_future(self.connect_stdin())
        self.connection = mock.Mock(name='ConnectionObject')
        asyncio.ensure_future(self.print_prompt())

    async def connect_stdin(self):
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(loop=loop)
        reader_protocol = asyncio.StreamReaderProtocol(reader)

        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

        while True:
            line = (await reader.readline()).rstrip().decode("utf-8")
            self.input_line = line
            if self.input_line is None or self.input_line == '':
                self.input_line = None
            await asyncio.sleep(0.1)
            asyncio.ensure_future(self.print_prompt())

    async def print_prompt(self):
        print('\033[4mbetabot\033[0m> ', end='')
        sys.stdout.flush()

    async def _get_next_event(self):
        if len(self._web_events):
            event = self._web_events.pop()
            return event

        while not self.input_line:
            await asyncio.sleep(0.001)  # sleep(0) here eats all cpu

        user_input = self.input_line
        self.input_line = None

        event = {'type': 'message',
                 'text': user_input}

        return event

    async def api(self, method, params=None):
        if not params:
            params = {}
        params.update({'token': self._token})
        api_url = 'https://slack.com/api/%s' % method

        request = '%s?%s' % (api_url, urlencode(params))
        LOG.info('Would send an API request: %s' % request)
        response = {
            "ts": time.time()
        }
        return response

    async def event_to_chat(self, event) -> Chat:
        return Chat(
            text=event['text'],
            user='User',
            channel=self._cli_channel,
            raw=event,
            bot=self)

    async def send(self, text, to, extra=None):
        print('\033[93m! betabot: \033[92m', text, '\033[0m')
        sys.stdout.flush()
        await asyncio.sleep(0.01)  # Avoid BlockingIOError due to sync print above.
        return await self.event_to_chat({'text': text})

    def get_channel(self, name):
        # https://api.slack.com/types/channel
        sample_info = {
            "id": "C024BE91L",
            "name": "fun",
            "is_channel": True,
            "created": 1360782804,
            "creator": "U024BE7LH",
            "is_archived": False,
            "is_general": False,

            "members": [
                "U024BE7LH",
            ],

            "topic": {
                "value": "Fun times",
                "creator": "U024BE7LV",
                "last_set": 1369677212
            },
            "purpose": {
                "value": "This channel is for fun",
                "creator": "U024BE7LH",
                "last_set": 1360782804
            },

            "is_member": True,

            "last_read": "1401383885.000061",
            "unread_count": 0,
            "unread_count_display": 0}
        return Channel(bot=self, info=sample_info)

    def find_channels(self, pattern):
        return []
