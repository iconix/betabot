import logging
import random

import asyncio
import dacite
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from betabot.bots.bot import Bot, InvalidOptions, dict_subset
from betabot.chat import Chat
from betabot.classes import Channel
from betabot import utility

# TODO: allow these logs with a -vv verbose arg
logging.getLogger('slack_bolt.AsyncApp').setLevel(logging.INFO)

LOG = logging.getLogger(__name__)


class BotSlack(Bot):
    engine = 'slack'
    _too_fast_warning = False

    def __init__(self, start_web_app=False) -> None:
        super().__init__(start_web_app)

    async def setup(self, memory_type, script_paths):
        await super().setup(memory_type, script_paths)

        app_token = utility.get_app_token()
        if not app_token:
            raise InvalidOptions('SLACK_APP_TOKEN required for slack engine.')

        self._handler = AsyncSocketModeHandler(self._bolt_app, app_token)

        # TODO: dataclass the response: {'ok': True, 'url': 'https://asappinc.slack.com/', 'team': 'ASAPP', 'user': 'lil_ann', 'team_id': 'T02SZCJU2', 'user_id': 'U01HMBB9ZNV', 'bot_id': 'B01H5KMBBU5', 'is_enterprise_install': False}
        identity = await self._bolt_app.client.auth_test()

        self._bot_id = identity.data.get('bot_id')
        self._user_id = identity.data.get('user_id')
        self._user = identity.data.get('user')

        await self._update_channels()
        await self._update_users()

        self._too_fast_warning = False

    async def start(self):
        await super().start()

        self._handler = AsyncSocketModeHandler(self._bolt_app, utility.get_app_token())
        return await self._handler.start_async()

    async def _setup(self):
        self._bolt_app: AsyncApp = AsyncApp(
            token=utility.get_bot_token(),
            raise_error_for_unhandled_request=True
        )
        self.client: AsyncWebClient = self._bolt_app.client

    def _get_user(self, uid) -> 'User':
        match = [u for u in self.users if u['id'] == uid]
        if match:
            return User(match[0])

    async def _update_users(self):
        # TODO: need `users:read`
        try:
            self.users = []
            next_cursor = True
            while next_cursor:
                if next_cursor is True:
                    next_cursor = ''

                response = (await self._bolt_app.client.users_list(limit=1000, cursor=next_cursor)).data
                self.users.extend(response.get('members'))
                next_cursor = response.get('response_metadata', {}).get('next_cursor')
        except SlackApiError as e:
            LOG.warning(f'users_list: {e}')

        LOG.info(f'bot loaded {len(self.users)} users')

    async def _update_channels(self):
        try:
            self.channels = {}
            next_cursor = True
            while next_cursor:
                if next_cursor is True:
                    next_cursor = ''

                response = (await self._bolt_app.client.conversations_list(limit=1000, cursor=next_cursor)).data
                self.channels = {**self.channels, **{c['id']: dacite.from_dict(Channel, c) for c in response.get('channels')}}
                next_cursor = response.get('response_metadata', {}).get('next_cursor')
        except SlackApiError as e:
            LOG.warning(f'conversations_list: {e}')

        # n.b., this also includes archived channels
        LOG.info(f"bot loaded {len(self.channels)} channels")

        # TODO: response = await self.api('groups.list')
        # self.channels.extend(response['groups'])

    async def event_to_chat(self, message):
        channel = self.get_channel(id=message.get('channel'))
        chat = Chat(text=message.get('text'),
                    user=message.get('user'),
                    channel=channel,
                    raw=message,
                    bot=self)
        return chat

    async def send(self, text, to, extra=None):
        if extra is None:
            extra = {}
        id = random.randint(1000, 10000)
        payload = {"id": id, "type": "message", "channel": to, "text": text}
        payload.update(extra)
        if self._too_fast_warning:
            await asyncio.sleep(2)
            self._too_fast_warning = False
        # TODO: await self.connection.write_message(json.dumps(payload))

        confirmation_event = await self.wait_for_event(reply_to=id)
        confirmation_event.update({
            'channel': to,
            'user': self._user_id
        })
        return await self.event_to_chat(confirmation_event)

    def get_channel(self, **kwargs) -> Channel:
        match = [c for c in self.channels if dict_subset(c, kwargs)]
        if len(match) == 1:
            channel = Channel(bot=self, info=match[0])
            return channel

        # Super Hack!
        if kwargs.get('id') and kwargs['id'][0] == 'D':
            # direct message
            channel = Channel(bot=self, info=kwargs)
            return channel

        LOG.warning('Channel match for %s length %s' % (kwargs, len(match)))

        channel = Channel(bot=self, info=kwargs)
        return channel
