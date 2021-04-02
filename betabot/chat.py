import logging
import re

import asyncio

from betabot.bots.bot import Bot
from betabot.channel import Channel

LOG = logging.getLogger(__name__)


class Chat(object):
    """Wrapper for Message, Bot and helpful functions.

    This gets passed to the receiving script's function.
    """

    def __init__(self, text: str, user: str, channel: Channel, raw: dict, bot: Bot):
        self.text = text
        self.user = user  # TODO: Create a User() object
        self.channel = channel
        self.bot = bot
        self.raw = raw

        self.is_direct = False

        self.listening = None
        self.heard_message = None

        self.regex_groups = None
        self.regex_group_dict = {}

    def matches_regex(self, regex, save=True):
        """Check if this message matches the regex with or without direct mention.

        If it does store the groups for later use.
        """
        if not self.text:
            return False

        is_private_message = self.channel.info.get('id').startswith('D')
        if is_private_message:
            self.is_direct = True

        flags = re.IGNORECASE

        match = re.match(f"^{regex}$", self.text, flags)
        if not match:
            regex_name = f'^[\\s@<]*(?:{self.bot._user_name}|{self.bot._user_id})[>:,\\s]*'

            starts_with_name = re.match(regex_name, self.text, flags)
            if starts_with_name:
                self.text = re.sub(regex_name, '', self.text, flags=flags)
                self.is_direct = True
                return self.matches_regex(regex, save)

            return False

        if save:
            self.regex_groups = match.groups()
            self.regex_group_dict = match.groupdict()
        LOG.debug(f"Chat matched regex: {self.text} matched {regex}")
        return True

    async def reply(self, text):
        """Reply to the original channel of the message."""
        # help hacks
        # help fix direct messages
        return await self.bot.send(text, to=self.channel.info.get('id'))

    async def reply_thread(self, text):
        """Reply to the original channel of the message in a thread."""
        return await self.bot.send(text, to=self.channel.info.get('id'),
                                   extra={'thread_ts': self.raw.get('ts')})

    async def react(self, reaction):
        # TODO: self.bot.react(reaction, chat=self)
        await self.bot.api('reactions.add', {
            'name': reaction,
            'timestamp': self.raw.get('ts'),
            'channel': self.channel.info.get('id')})

    async def button_prompt(self, text, buttons):
        return await self.channel.button_prompt(text, buttons)

    # TODO: Add a timeout here. Don't want to hang forever.
    async def listen_for(self, regex: str):
        self.listening = regex

        # Hang until self.hear() sets this to False
        self.bot.add_listener(self)
        while self.listening:
            await asyncio.sleep(0.01)
        self.bot._remove_listener(self)

        return self.heard_message

    async def hear(self, new_message):
        """Invoked by the Bot class to note that `message` was heard."""

        # TODO: some flag should control this filter
        if new_message.user != self.user:
            LOG.debug('Heard this from a wrong user.')
            return

        match = re.match(self.listening, new_message.text)
        if match:
            self.listening = None
            self.heard_message = new_message
            return
