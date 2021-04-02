import json
import logging
import os
import random
from urllib.parse import urlencode

import asyncio
from tornado import httpclient, websocket

from betabot.bots.bot import Bot, CoreException, InvalidOptions, dict_subset

LOG = logging.getLogger(__name__)


class BotSlack(Bot):
    engine = 'slack'
    _too_fast_warning = False

    async def _setup(self):
        self._token = os.getenv('SLACK_TOKEN')

        if not self._token:
            raise InvalidOptions('SLACK_TOKEN required for slack engine.')

        LOG.info('Authenticating...')
        try:
            response = await self.api('rtm.start')
        except Exception as e:
            raise CoreException('API call "rtm.start" to Slack failed: %s' % e)

        if response['ok']:
            LOG.info('Logged in!')
        else:
            LOG.error('Login failed. Reason: "{}". Payload dump: {}'.format(
                response.get('error', 'No error specified'), response))
            raise InvalidOptions('Login failed')

        self.socket_url = response['url']
        self.connection = await websocket.websocket_connect(self.socket_url)

        self._user_id = response['self']['id']
        self._user_name = response['self']['name']

        await self._update_channels()
        await self._update_users()

        self._too_fast_warning = False

    def _get_user(self, uid) -> 'User':
        match = [u for u in self._users if u['id'] == uid]
        if match:
            return User(match[0])

    async def _update_users(self):
        response = await self.api('users.list')
        self._users = response['members']

    async def _update_channels(self):
        response = await self.api('channels.list')
        self._channels = response['channels']
        response = await self.api('groups.list')
        self._channels.extend(response['groups'])

    async def event_to_chat(self, message):
        channel = self.get_channel(id=message.get('channel'))
        chat = Chat(text=message.get('text'),
                    user=message.get('user'),
                    channel=channel,
                    raw=message,
                    bot=self)
        return chat

    async def _get_next_event(self):
        """Slack-specific message reader.

        Returns a web event from the API listener if available, otherwise
        waits for the slack streaming event.
        """

        if len(self._web_events):
            event = self._web_events.pop()
            return event

        # TODO: rewrite this logic to use `on_message` feature of the socket
        # FIXME: At the moment if there are 0 socket messages then web_events
        #        will never be handled.
        message = await self.connection.read_message()
        LOG.debug('Slack message: "%s"' % message)
        message = json.loads(message)

        return message

    async def api(self, method, params=None):
        client = httpclient.AsyncHTTPClient()
        if not params:
            params = {}
        params.update({'token': self._token})
        api_url = 'https://slack.com/api/%s' % method

        request = '%s?%s' % (api_url, urlencode(params))
        response = await client.fetch(request=request)
        return json.loads(response.body)

    async def send(self, text, to, extra=None):
        if extra is None:
            extra = {}
        id = random.randint(1000, 10000)
        payload = {"id": id, "type": "message", "channel": to, "text": text}
        payload.update(extra)
        if self._too_fast_warning:
            await asyncio.sleep(2)
            self._too_fast_warning = False
        await self.connection.write_message(json.dumps(payload))

        confirmation_event = await self.wait_for_event(reply_to=id)
        confirmation_event.update({
            'channel': to,
            'user': self._user_id
        })
        return await self.event_to_chat(confirmation_event)

    def get_channel(self, **kwargs):
        match = [c for c in self._channels if dict_subset(c, kwargs)]
        if len(match) == 1:
            channel = Channel(bot=self, info=match[0])
            return channel

        # Super Hack!
        if kwargs.get('id') and kwargs['id'][0] == 'D':
            # Direct message
            channel = Channel(bot=self, info=kwargs)
            return channel

        LOG.warning('Channel match for %s length %s' % (kwargs, len(match)))
