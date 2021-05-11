from dataclasses import dataclass
import logging
import re
from typing import Any, Awaitable, Callable, Dict, Optional

from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.async_context import AsyncBoltContext
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_bolt.response import BoltResponse

from slack_sdk.web.async_client import AsyncWebClient

LOG = logging.getLogger(__name__)
RE_FLAGS = flags = re.IGNORECASE


@dataclass
class EventActions(object):
    ack: AsyncAck
    say: AsyncSay
    respond: AsyncRespond
    next: Callable[[], Awaitable[None]]


@dataclass
class EventContext(object):
    client: AsyncWebClient
    request: AsyncBoltRequest
    response: BoltResponse
    context: AsyncBoltContext
    bot: Any  # TODO: Bot


@dataclass
class EventData(object):
    body: Dict[str, Any]
    payload: Dict[str, Any]
    options: Optional[Dict[str, Any]]
    shortcut: Optional[Dict[str, Any]]
    action: Optional[Dict[str, Any]]
    view: Optional[Dict[str, Any]]
    command: Optional[Dict[str, Any]]
    event: Optional[Dict[str, Any]]
    message: Optional[Dict[str, Any]]


class Event(object):
    """Wrapper for Event and helpful functions.

    This gets passed to the receiving script's function.
    """

    def __init__(self, *, actions: EventActions, context: EventContext, data: EventData, **kwargs):
        self.actions = actions
        self.context = context
        self.data = data
        self.kwargs = kwargs

        self.type = data.event.get('type')
        self.channel = data.event.get('channel')  # TODO: use the Channel object?
        self.user = data.event.get('user')  # TODO: use the User object?
        self.text = data.event.get('text')
        self.ts = data.event.get('ts')

        self.bot = self.context.bot

        self.is_direct = False
        self._set_direct()

        self.regex_groups = None
        self.regex_group_dict = {}

    def _set_direct(self):
        """Check if this message is a direct mention or private message to bot.
        """
        if not self.text:
            return

        # TODO: the following should be treated as direct:
        #   - private messages

        # all BotCLI events
        is_cli = self.channel == 'CLI'
        if is_cli:
            self.is_direct = True

        # all app mentions
        if self.data.event.get('type') == 'app_mention':
            self.is_direct = True

        # app mentions
        regex_name = f'[\\s@<]*(?:{self.bot._user}|{self.bot._user_id})[>:,\\s]*'

        contains_mention = re.search(regex_name, self.text, RE_FLAGS)
        if contains_mention:
            self.text = re.sub(regex_name, '', self.text, flags=RE_FLAGS)
            self.is_direct = True

    def match_regex(self, regex: re.Pattern) -> bool:
        match = regex.search(self.text)
        if match:
            self.regex_groups = match.groups()
            self.regex_group_dict = match.groupdict()
            LOG.debug(f"Chat matched regex: {self.text} matched {regex}")

        return True if match else False
