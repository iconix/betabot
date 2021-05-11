from datetime import datetime
import logging
import mock
import re
import sys
from typing import Optional, Union

import asyncio
from slack_bolt.async_app import AsyncApp
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_sdk.web.async_client import AsyncWebClient

from betabot.bots.bot import Bot

from betabot.classes import Channel

LOG = logging.getLogger(__name__)


class BotCLI(Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mock_client = mock.Mock(spec=AsyncWebClient)
        mock_client.token = 'xoxb-xxx'
        self._bolt_app = AsyncApp(
            client=mock_client,
            raise_error_for_unhandled_request=True
        )

        # TODO: User object?
        self._user = re.sub(r'\..*', '', sys.modules[__name__].__package__)
        self._user_id = 'U123'
        # TODO: self._channel = Channel(self, {'id': 'CLI'}) ?
        self._channel = 'CLI'
        self._stdin = None

    async def setup(self, memory_type, script_paths):
        await super().setup(memory_type, script_paths)

        asyncio.ensure_future(self._connect_stdin())
        asyncio.ensure_future(self._print_prompt())

    async def _connect_stdin(self):
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(loop=loop)
        reader_protocol = asyncio.StreamReaderProtocol(reader)

        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

        while True:
            line = (await reader.readline()).rstrip().decode('utf-8')
            self._stdin = line
            if self._stdin is None or self._stdin == '':
                self._stdin = None
            await asyncio.sleep(0.1)
            asyncio.ensure_future(self._print_prompt())

    async def _print_prompt(self):
        print(f'\033[4m{self._user}\033[0m> ', end='')
        sys.stdout.flush()

    async def start(self):
        await super().start()

        while True:
            event = await self._get_next_event()

            async def say(text: Union[str, dict], channel: Optional[str] = None, thread_ts: Optional[str] = None,):
                add_whitespace = '\n' if '\n' in text else ' '
                print(f'\033[93m! {self._user}:{add_whitespace}\033[92m{text}\033[0m')
                sys.stdout.flush()
                await asyncio.sleep(0.01)  # avoid BlockingIOError due to sync print above

                # TODO: AsyncSlackResponse
                return {
                    'text': text,
                    'channel': channel,
                    'thread_ts': thread_ts,
                }

            req: AsyncBoltRequest = AsyncBoltRequest(
                mode='socket_mode',
                body={
                    'event': event,
                    'type': 'event_callback'
                },
                context={
                    'say': say
                }
            )
            await self._bolt_app.async_dispatch(req)

    async def _get_next_event(self):
        while not self._stdin:
            await asyncio.sleep(0.001)  # sleep(0) here eats all cpu

        user_input = self._stdin
        self._stdin = None

        ts = str(datetime.now().timestamp())
        # https://api.slack.com/events/message
        return {
            'type': 'message',
            'channel': self._channel,
            'user': self._user,
            'team_id': self._channel,
            'text': user_input,
            'ts': ts
        }

    async def send(self, text, to, extra=None):
        print('\033[93m! betabot: \033[92m', text, '\033[0m')
        sys.stdout.flush()
        await asyncio.sleep(0.01)  # avoid BlockingIOError due to sync print above.
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
