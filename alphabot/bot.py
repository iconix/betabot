from __future__ import print_function

import StringIO
import json
import logging
import os
import pkgutil
import re
import sys
import traceback
import urllib

from apscheduler.schedulers.tornado import TornadoScheduler
from tornado import websocket, gen, httpclient, ioloop
import requests

from alphabot import memory

DEFAULT_SCRIPT_DIR = 'default-scripts'

log = logging.getLogger(__name__)
scheduler = TornadoScheduler()
scheduler.start()


def dict_subset(big, small):
    try:
        return small.viewitems() <= big.viewitems()  # Python 2.7
    except AttributeError:
        return small.items() <= big.items()  # Python 3


class AlphaBotException(Exception):
    """Top of hierarchy for all alphabot failures."""


class CoreException(AlphaBotException):
    """Used to signify a failure in the robot's core."""


class InvalidOptions(AlphaBotException):
    """Robot failed because input options were somehow broken."""


def get_instance(engine='cli'):
    if not Bot.instance:
        engine_map = {
            'cli': BotCLI,
            'slack': BotSlack
        }
        if not engine_map.get(engine):
            raise InvalidOptions('Bot engine "%s" is not available.' % engine)

        log.debug('Creating a new bot instance. engine: %s' % engine)
        Bot.instance = engine_map.get(engine)()

    return Bot.instance


def load_all_modules_from_dir(dirname):
    log.debug('Loading modules from "%s"' % dirname)
    for importer, package_name, _ in pkgutil.iter_modules([dirname]):
        log.debug("Importing '%s'" % package_name)
        importer.find_module(package_name).load_module(package_name)


def handle_exceptions(future, chat):
    """Attach to Futures that are not yielded."""

    if not hasattr(future, 'add_done_callback'):
        log.error('Could not attach callback. Exceptions will be missed.')
        return

    def cb(future):
        """Custom callback which is chat aware."""
        try:
            future.result()
        except Exception as e:
            log.error('Script had an error', exc_info=1)

            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_string = StringIO.StringIO()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      file=traceback_string)
            chat.reply('Script had an error: %s ```%s```' % (e, traceback_string.getvalue()))

    # Tornado functionality to add a custom callback
    future.add_done_callback(cb)


class Bot(object):

    instance = None
    engine = 'default'

    def __init__(self):
        self.memory = None
        self.event_listeners = []
        self._on_start = []
        self._channel_names = {}
        self._channel_ids = {}

    @gen.coroutine
    def setup(self, memory_type, script_paths):
        yield self._setup_memory(memory_type=memory_type)
        yield self._setup()  # Engine specific setup
        yield self._gather_scripts(script_paths)

    @gen.coroutine
    def _setup_memory(self, memory_type='dict'):

        # TODO: memory module should provide this mapping.
        memory_map = {
            'dict': memory.MemoryDict,
            'redis': memory.MemoryRedis,
        }

        # Get associated memory class or default to Dict memory type.
        MemoryClass = memory_map.get(memory_type)
        if not MemoryClass:
            raise InvalidOptions(
                'Memory type "%s" is not available.' % memory_type)

        self.memory = MemoryClass()
        yield self.memory.setup()

    @gen.coroutine
    def _gather_scripts(self, script_paths=[]):
        log.info('Gathering scripts...')
        for path in script_paths:
            log.info('Gathering functions from %s' % path)
            load_all_modules_from_dir(path)
        if not script_paths:
            log.warning('Warning! You did not specify any scripts to load.')

        log.info('Installing default scripts...')
        pwd = os.path.dirname(os.path.realpath(__file__))
        load_all_modules_from_dir(
            "{path}/{default}".format(path=pwd, default=DEFAULT_SCRIPT_DIR))

    @gen.coroutine
    def start(self):

        log.info('Executing the start scripts.')
        for function in self._on_start:
            function()

        log.info('Bot started! Listening to events.')

        while True:
            event = yield self._get_next_event()
            log.debug('Received event: %s' % event)
            log.debug('Checking against %s listeners' % len(self.event_listeners))

            # Note: Copying the event_listeners list here to prevent
            # mid-loop modification of the list.
            for kwargs, function in list(self.event_listeners):
                log.debug('Checking "%s"' % function.__name__)
                log.debug('Searching for %s in %s' % (kwargs, event))
                match = self._check_event_kwargs(event, kwargs)
                if match:
                    log.debug("It's a match!")
                    # XXX Rethink creating a chat object
                    chat = yield self.event_to_chat(event)
                    future = function(event=event)
                    handle_exceptions(future, chat)
                yield gen.moment

    def _add_listener(self, chat):
        log.info('Adding chat listener...')

        @gen.coroutine
        def cmd(event):
            message = yield self.event_to_chat(event)
            chat.hear(message)

        # Uniquely identify this `cmd` to delete later.
        cmd._listener_chat_id = id(chat)

        self.on(type='message')(cmd)

    def _remove_listener(self, chat):
        match = None
        # Have to search all the event_listeners here
        for kw, function in self.event_listeners:
            if (hasattr(function, '_listener_chat_id') and
                    function._listener_chat_id == id(chat)):
                match = (kw, function)
        self.event_listeners.remove(match)

    def _check_event_kwargs(self, event, kwargs):
        """Check that all expected kwargs were satisfied by the event."""
        return dict_subset(event, kwargs)

    # Decorators to be used in development of scripts

    def on_start(self, function):
        self._on_start.append(function)

    def on(self, **kwargs):
        def decorator(function):
            log.info('New Listener: %s => %s()' % (kwargs, function.__name__))
            self.event_listeners.append((kwargs, function))

        return decorator

    def add_command(self, regex, direct=False):
        def decorator(function):
            @gen.coroutine
            def cmd(event):
                message = yield self.event_to_chat(event)
                matches_regex = message.matches_regex(regex)
                if not direct and not matches_regex:
                    return

                if direct:
                    # TODO maybe make it better...
                    # TODO definitely refactor this garbage: message.is_direct()
                    # or better yet: message.matches(regex, direct)
                    # Here's how Hubot did it:
                    # https://github.com/github/hubot/blob/master/src/robot.coffee#L116
                    is_direct = False
                    # is_direct = (message.channel.startswith('D') or
                    #             message.matches_regex("^@?%s:?\s" % self._user_id, save=False))
                    if not is_direct:
                        return
                yield function(message)
            cmd.__name__ = function.__name__

            self.on(type='message')(cmd)

        return decorator

    def on_schedule(self, **schedule_keywords):
        """Invoke bot command on a schedule.

        Leverages APScheduler for Tornado.
        http://apscheduler.readthedocs.io/en/latest/modules/triggers/cron.html#api

        year (int|str) - 4-digit year
        month (int|str) - month (1-12)
        day (int|str) - day of the (1-31)
        week (int|str) - ISO week (1-53)
        day_of_week (int|str) - number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun)
        hour (int|str) - hour (0-23)
        minute (int|str) - minute (0-59)
        second (int|str) - second (0-59)
        start_date (datetime|str) - earliest possible date/time to trigger on (inclusive)
        end_date (datetime|str) - latest possible date/time to trigger on (inclusive)
        timezone (datetime.tzinfo|str) - time zone to use for the date/time calculations
        (defaults to scheduler timezone)
        """

        if 'second' not in schedule_keywords:
            # Default is every second. We don't want that.
            schedule_keywords['second'] = '0'

        def decorator(function):
            log.info('New Schedule: cron[%s] => %s()' % (schedule_keywords,
                                                         function.__name__))
            scheduler.add_job(function, 'cron', **schedule_keywords)

        return decorator

    # Functions that scripts can tell bot to execute.

    @gen.coroutine
    def send(self, text, to):
        raise CoreException('Chat engine "%s" is missing send(...)' % (
            self.__class__.__name__))

    @gen.coroutine
    def _update_channels(self):
        raise CoreException('Chat engine "%s" is missing _update_channels(...)' % (
            self.__class__.__name__))

    def get_channel(self, name):
        raise CoreException('Chat engine "%s" is missing get_channel(...)' % (
            self.__class__.__name__))

    def find_channels(self, pattern):
        raise CoreException('Chat engine "%s" is missing find_channels(...)' % (
            self.__class__.__name__))


class BotCLI(Bot):

    @gen.coroutine
    def _setup(self):
        self.print_prompt()
        ioloop.IOLoop.instance().add_handler(
            sys.stdin, self.capture_input, ioloop.IOLoop.READ)

        self.input_line = None
        self._user_id = 'alphabot'

    def print_prompt(self):
        print('\033[4mAlphabot\033[0m> ', end='')

    def capture_input(self, fd, events):
        self.input_line = fd.readline().strip()
        if self.input_line is None or self.input_line == '':
            self.input_line = None
        self.print_prompt()

    @gen.coroutine
    def _get_next_event(self):
        while not self.input_line:
            yield gen.moment

        user_input = self.input_line
        self.input_line = None

        event = {'type': 'message',
                 'message': user_input}

        raise gen.Return(event)

    @gen.coroutine
    def event_to_chat(self, event):
        return Chat(
            text=event['message'],
            user='User',
            channel=Channel(self, {'id': 'CLI'}),
            raw=event['message'],
            bot=self)

    @gen.coroutine
    def send(self, text, to):
        print('\033[93mAlphabot: \033[92m', text, '\033[0m')

    def get_channel(self, name):
        return Channel(bot=self, info={})

    def find_channels(self, pattern):
        return []


class BotSlack(Bot):

    engine = 'slack'

    @gen.coroutine
    def _setup(self):
        api_start = 'https://slack.com/api/rtm.start'
        self._token = os.getenv('SLACK_TOKEN')
        if not self._token:
            raise InvalidOptions('SLACK_TOKEN required for slack engine.')

        log.info('Authenticating...')
        response = requests.get(api_start + '?token=' + self._token).json()
        log.info('Logged in!')

        self.socket_url = response['url']
        self.connection = yield websocket.websocket_connect(self.socket_url)

        self._user_id = response['self']['id']
        self._channels = response['channels']

        self._too_fast_warning = False

    @gen.coroutine
    def _update_channels(self):
        api_list = 'https://slack.com/api/channels.list'

        client = httpclient.AsyncHTTPClient()
        # TODO: make a bot command for tokenized fetch
        response = yield client.fetch(api_list + '?token=' + self._token)
        channels = json.loads(response.body)['channels']

        self._channels = channels

    @gen.coroutine
    def event_to_chat(self, message):
        channel = self.get_channel(id=message.get('channel'))
        chat = Chat(text=message.get('text'),
                    user=message.get('user'),
                    channel=channel,
                    raw=message,
                    bot=self)
        raise gen.Return(chat)

    @gen.coroutine
    def _get_next_event(self):
        """Slack-specific message reader."""
        message = yield self.connection.read_message()
        log.info(message)

        message = json.loads(message)

        raise gen.Return(message)

    @gen.coroutine
    def send(self, text, to):
        payload = json.dumps({
            "id": 1,
            "type": "message",
            "channel": to,
            "text": text
        })
        log.debug(payload)
        if self._too_fast_warning:
            yield gen.sleep(2)
            self._too_fast_warning = False
        yield self.connection.write_message(payload)
        yield gen.sleep(0.1)  # A small sleep here to allow Slack to respond

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

        log.warning('Channel match for %s length %s' % (kwargs, len(match)))


class Channel(object):

    def __init__(self, bot, info):
        self.bot = bot
        self.info = info

    @gen.coroutine
    def send(self, text):
        # TODO: Help make this slack-specfic...
        yield self.bot.send(text, self.info.get('id'))


class Chat(object):
    """Wrapper for Message, Bot and helpful functions.

    This gets passed to the receiving script's function.
    """

    def __init__(self, text, user, channel, raw, bot):
        self.text = text
        self.user = user  # TODO: Create a User() object
        self.channel = channel
        self.bot = bot
        self.raw = raw
        self.listening = False
        self.regex_groups = None

    def matches_regex(self, regex, save=True):
        """Check if this message matches the regex.

        If it does store the groups for later use.
        """
        if not self.text:
            return False
        match = re.match(regex, self.text, flags=re.IGNORECASE)
        if not match:
            return False

        if save:
            self.regex_groups = match.groups()
        return True

    @gen.coroutine
    def reply(self, text):
        """Reply to the original channel of the message."""
        # help hacks
        # help fix direct messages
        yield self.bot.send(text, to=self.channel.info.get('id'))

    # TODO: figure out how to make this Slack-specific
    @gen.coroutine
    def react(self, reaction):
        api_react = 'https://slack.com/api/reactions.add'

        # TODO: self.bot.react(reaction, chat=self)
        client = httpclient.AsyncHTTPClient()
        yield client.fetch((
            api_react +
            '?token=' + self.bot._token +
            '&name=' + reaction +
            '&timestamp=' + self.raw.get('ts') +
            '&channel=' + self.channel.info.get('id')))

    @gen.coroutine
    def button_prompt(self, text, buttons):
        api_button = 'https://slack.com/api/chat.postMessage'

        button_actions = []
        for b in buttons:
            if type(b) == dict:
                button_actions.append(b)
            else:
                # assuming it's a string
                button_actions.append({
                    "type": "button",
                    "text": b,
                    "name": b,
                    "value": b
                })

        attachment = [{
            "color": "#1E9E5E",
            "text": text,
            "actions": button_actions,
            "callback_id": id(self),
            "fallback": "You are unable to choose for this.",
            "attachment_type": "default"
        }]

        client = httpclient.AsyncHTTPClient()
        response = yield client.fetch(
            request='%s?%s' % (api_button, urllib.urlencode({
                'token': self.bot._token,
                'attachments': json.dumps(attachment),
                'channel': self.channel.info.get('id')})),
            raise_error=False
        )

        # TODO: Add logic to wait for the response for this specific button!

    # TODO: Add a timeout here. Don't want to hang forever.
    @gen.coroutine
    def listen_for(self, regex):
        self.listening = regex

        # Hang until self.hear() sets this to False
        self.bot._add_listener(self)
        while self.listening:
            yield gen.moment
        self.bot._remove_listener(self)

        raise gen.Return(self.heard_message)

    @gen.coroutine
    def hear(self, new_message):
        """Invoked by the Bot class to note that `message` was heard."""

        # TODO: some flag should control this filter
        if new_message.user != self.user:
            log.debug('Heard this from a wrong user.')
            return

        match = re.match(self.listening, new_message.text)
        if match:
            self.listening = False
            self.heard_message = new_message
            raise gen.Return()
