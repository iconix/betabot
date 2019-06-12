from __future__ import print_function

import asyncio
import json
import logging
import os
import pkgutil
import re
import sys
import time
import traceback
from io import StringIO

import mock

try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tornado import websocket, httpclient, web

from alphabot import help
from alphabot import memory

DEFAULT_SCRIPT_DIR = 'default-scripts'
DEBUG_CHANNEL = os.getenv('DEBUG_CHANNEL', 'alphabot')

WEB_PORT = int(os.getenv('WEB_PORT', 8000))
WEB_NO_SSL = os.getenv('WEB_NO_SSL', '') != ''
WEB_PORT_SSL = int(os.getenv('WEB_PORT_SSL', 8443))

log = logging.getLogger(__name__)
log_level = logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
log.setLevel(log_level)
scheduler = AsyncIOScheduler()
scheduler.start()


class AlphaBotException(Exception):
    """Top of hierarchy for all alphabot failures."""


class CoreException(AlphaBotException):
    """Used to signify a failure in the robot's core."""


class InvalidOptions(AlphaBotException):
    """Robot failed because input options were somehow broken."""


class WebApplicationNotAvailable(AlphaBotException):
    """Failed to register web handler because no web app registered."""


def get_instance(engine='cli', start_web_app=False):
    """Get an Alphabot instance.

    Args:
        engine (str): Type of Alphabot to create ('cli', 'slack')
        start_web_app (bool): Whether to start a web server with the engine.

    Returns:
        Bot: An Alphabot instance.
    """
    if not Bot.instance:
        engine_map = {
            'cli': BotCLI,
            'slack': BotSlack
        }
        if not engine_map.get(engine):
            raise InvalidOptions('Bot engine "%s" is not available.' % engine)

        log.debug('Creating a new bot instance. engine: %s' % engine)
        Bot.instance = engine_map.get(engine)(start_web_app=start_web_app)

    return Bot.instance


def handle_exceptions(future, chat):
    """Attach to Futures that are not yielded."""

    if not hasattr(future, 'add_done_callback'):
        log.error('Could not attach callback. Exceptions will be missed.')
        return

    def cb(future):
        """Custom callback which is chat aware."""
        try:
            future.result()
        except AlphaBotException as e:
            """This exception was raised intentionally. No need for traceback."""
            if chat:
                chat.reply('Script had an error: %s' % e)
            else:
                log.error('Script had an error: %s' % e)
        except Exception as e:
            log.critical('Script had an error: %s' % e, exc_info=1)

            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_string = StringIO()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      file=traceback_string)

            if chat:
                chat.reply('Script had an error: %s ```%s```' % (e, traceback_string.getvalue()))

    # Tornado functionality to add a custom callback
    future.add_done_callback(cb)


def dict_subset(big, small):
    try:
        return small.viewitems() <= big.viewitems()  # Python 2.7
    except AttributeError:
        return small.items() <= big.items()  # Python 3


class MetaString(str):
    _meta = dict()


class HealthCheck(web.RequestHandler):
    """An endpoint used to check if the app is up."""

    def get(self):
        self.write('ok')


class Bot(object):
    instance = None
    engine = 'default'

    def __init__(self, start_web_app=False):
        self.memory = None
        self.event_listeners = []
        self._web_events = []
        self._on_start = []

        self.help = help.Help()
        self._function_map = {}
        self._web_app = None
        if start_web_app:
            self._web_app = self.make_web_app()

    @staticmethod
    def make_web_app():
        """Creates a web application.

        Returns:
            web.Application.
        """
        log.info('Creating a web app')
        return web.Application([
            (r'/health_check', HealthCheck)
        ])

    def _start_web_app(self):
        """Creates a web server on WEB_PORT and WEB_PORT_SSL

        Args:
            http_port (int): Port to use for HTTP.
            ssl_port (int): Port to use for HTTPS.
        """
        if not self._web_app:
            return
        log.info('Listing on port %s' % WEB_PORT)
        self._web_app.listen(WEB_PORT)
        if not WEB_NO_SSL:
            try:
                self._web_app.listen(WEB_PORT_SSL, ssl_options={
                    "certfile": "/tmp/alphabot.pem",  # Generate these in your entrypoint
                    "keyfile": "/tmp/alphabot.key"
                })
            except ValueError as e:
                log.error(e)
                log.error('Failed to start SSL web app on %s. To disable - set WEB_NO_SSL',
                          WEB_PORT_SSL)

    def add_web_handler(self, path, handler):
        """Adds a Handler to a web app.

        Args:
            path (string): Path where the handler should be served.
            handler (web.RequestHandler): Handler to use.

        Raises:
            WebApplicationNotAvailable
        """
        if not self._web_app:
            raise WebApplicationNotAvailable

        self._web_app.add_handlers('.*', [(path, handler)])

    async def setup(self, memory_type, script_paths):
        await self._setup_memory(memory_type=memory_type)
        await self._setup()  # Engine specific setup
        await self._gather_scripts(script_paths)

    async def _setup_memory(self, memory_type='dict'):

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
        await self.memory.setup()

    def load_all_modules_from_dir(self, dirname):
        log.debug('Loading modules from "%s"' % dirname)
        for importer, package_name, _ in pkgutil.iter_modules([dirname]):
            self.module_path = "%s/%s" % (dirname, package_name)
            log.debug("Importing '%s'" % package_name)
            try:
                importer.find_module(package_name).load_module(package_name)
            except Exception as e:
                log.critical('Could not load `%s`. Error follows.' % package_name)
                log.critical(e, exc_info=1)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback_string = StringIO()
                traceback.print_exception(exc_type, exc_value, exc_traceback,
                                          file=traceback_string)
                asyncio.ensure_future(
                    self.send(
                        'Could not load `%s` from %s.' % (package_name, dirname),
                        DEBUG_CHANNEL)
                )

                asyncio.ensure_future(
                    self.send(traceback_string.getvalue(), DEBUG_CHANNEL)
                )

    async def _gather_scripts(self, script_paths=[]):
        log.info('Gathering scripts...')
        for path in script_paths:
            log.info('Gathering functions from %s' % path)
            self.load_all_modules_from_dir(path)

        if not script_paths:
            log.warning('Warning! You did not specify any scripts to load.')

        # TODO: Add a flag to control these
        log.info('Installing default scripts...')
        pwd = os.path.dirname(os.path.realpath(__file__))
        self.load_all_modules_from_dir(
            "{path}/{default}".format(path=pwd, default=DEFAULT_SCRIPT_DIR))

    def _event(self, payload):
        log.info('Adding an event on top of the stack: %s' % payload)
        self._web_events.append(payload)

    async def start(self):
        if self._web_app:
            log.info('Starting web app.')
            self._start_web_app()

        log.info('Executing the start scripts.')
        for func in self._on_start:
            log.debug('On Start: %s' % func.__name__)
            await func()

        log.info('Bot started! Listening to events.')

        while True:
            event = await self._get_next_event()

            log.debug('Received event: %s' % event)
            log.debug('Checking against %s listeners' % len(self.event_listeners))

            event_matched = False

            # Note: Copying the event_listeners list here to prevent
            # mid-loop modification of the list.
            for kwargs, func in list(self.event_listeners):
                match = self._check_event_kwargs(event, kwargs)
                log.debug('Function %s requires %s. Match: %s' % (
                    func.__name__, kwargs, match))
                if match:
                    event_matched = True
                    # XXX Rethink creating a chat object. Only using it for error handling
                    # chat = await self.event_to_chat(event)
                    future = func(event=event)
                    # handle_exceptions(future, chat)
                    asyncio.ensure_future(future)

            if not event_matched:
                # Add no-match handler. Mainly for Fallbakc like API.AI
                # Maybe add @bot.fallback() ?
                # But there should be only one fallback handler
                pass

    async def wait_for_event(self, **event_args):
        # Demented python scope.
        # http://stackoverflow.com/questions/4851463/python-closure-write-to-variable-in-parent-scope
        # This variable could be an object, but instead it's a single-element list.
        event_matched = []

        async def mark_true(event):
            event_matched.append(event)

        log.info('Creating a temporary listener for %s' % (event_args,))
        self.event_listeners.append((event_args, mark_true))

        while not event_matched:
            await asyncio.sleep(0.01)

        log.info('Deleting the temporary listener for %s' % (event_args,))
        self.event_listeners.remove((event_args, mark_true))

        return event_matched[0]

    def add_listener(self, chat, **kwargs):
        log.info('Adding chat listener...')

        async def cmd(event):
            message = await self.event_to_chat(event)
            asyncio.ensure_future(chat.hear(message))

        # Uniquely identify this `cmd` to delete later.
        cmd._listener_chat_id = id(chat)

        if 'type' not in kwargs:
            kwargs['type'] = 'message'

        self._register_function(kwargs, cmd)

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
        return function

    def _register_function(self, kwargs, function):
        log.debug('New Listener: %s => %s()' % (kwargs, function.__name__))
        self.event_listeners.append((kwargs, function))

    def _register_api_call(self, function):
        function_api_name = "alphabot:%s:%s" % (self.module_path, function.__name__)
        log.debug('Registering api: %s' % function_api_name)
        self._function_map.update({function_api_name: function})

    def on(self, **kwargs):
        """This decorator will invoke your function with the raw event."""

        def decorator(function):
            self._register_function(kwargs, function)
            self._register_api_call(function)
            return function

        return decorator

    def add_command(self, regex, direct=False):
        """Will convert the raw event into a message object for your function."""

        def decorator(function):
            # Register some basic help using the regex.
            self.help.update(function, regex)

            async def cmd(event):
                message = await self.event_to_chat(event)
                matches_regex = message.matches_regex(regex)
                log.debug('Command %s should match the regex %s' % (function.__name__, regex))
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
                await function(message=message, **message.regex_group_dict)

            cmd.__name__ = 'wrapped:%s' % function.__name__

            self._register_function({'type': 'message'}, cmd)
            self._register_api_call(function)
            return function

        return decorator

    def add_help(self, desc=None, usage=None, tags=None):
        def decorator(function):
            self.help.update(function, usage=usage, desc=desc, tags=tags)
            return function

        return decorator

    def on_schedule(self, **schedule_keywords):
        """Invoke bot command on a schedule.

        Leverages APScheduler for asyncio.
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

            scheduler.add_job(function, trigger='cron', **schedule_keywords)
            return function

        return decorator

    # Functions that scripts can tell bot to execute.

    async def event_to_chat(self, event):
        raise CoreException('Chat engine "%s" is missing event_to_chat(...)' % (
            self.__class__.__name__))

    async def send(self, text, to):
        raise CoreException('Chat engine "%s" is missing send(...)' % (
            self.__class__.__name__))

    async def _update_channels(self):
        raise CoreException('Chat engine "%s" is missing _update_channels(...)' % (
            self.__class__.__name__))

    def get_channel(self, name):
        raise CoreException('Chat engine "%s" is missing get_channel(...)' % (
            self.__class__.__name__))

    def find_channels(self, pattern):
        raise CoreException('Chat engine "%s" is missing find_channels(...)' % (
            self.__class__.__name__))


class BotCLI(Bot):

    async def _setup(self):
        self.print_prompt()

        asyncio.ensure_future(self.connect_stdin())

        self.input_line = None
        self._user_id = 'U123'
        self._user_name = 'alphabot'
        self._token = ''

        self.connection = mock.Mock(name='ConnectionObject')

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
            self.print_prompt()

    def print_prompt(self):
        print('\033[4mAlphabot\033[0m> ', end='')
        sys.stdout.flush()

    async def _get_next_event(self):
        if len(self._web_events):
            event = self._web_events.pop()
            return event

        while not self.input_line:
            await asyncio.sleep(0.01)  # sleep(0) here eats all cpu

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
        log.info('Would send an API request: %s' % request)
        response = {
            "ts": time.time()
        }
        return response

    async def event_to_chat(self, event):
        return Chat(
            text=event['text'],
            user='User',
            channel=Channel(self, {'id': 'CLI'}),
            raw=event,
            bot=self)

    async def send(self, text, to):
        print('\033[93mAlphabot: \033[92m', text, '\033[0m')

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


class BotSlack(Bot):
    engine = 'slack'
    _too_fast_warning = False

    async def _setup(self):
        self._token = os.getenv('SLACK_TOKEN')

        if not self._token:
            raise InvalidOptions('SLACK_TOKEN required for slack engine.')

        log.info('Authenticating...')
        try:
            response = await self.api('rtm.start')
        except Exception as e:
            raise CoreException('API call "rtm.start" to Slack failed: %s' % e)

        if response['ok']:
            log.info('Logged in!')
        else:
            log.error('Login failed. Reason: "{}". Payload dump: {}'.format(
                response.get('error', 'No error specified'), response))
            raise InvalidOptions('Login failed')

        self.socket_url = response['url']
        self.connection = await websocket.websocket_connect(self.socket_url)

        self._user_id = response['self']['id']
        self._user_name = response['self']['name']

        await self._update_channels()
        await self._update_users()

        self._too_fast_warning = False

    def _get_user(self, uid):
        match = [u for u in self._users if u['id'] == uid]
        if match:
            return User(match[0])

        # TODO: handle this better?
        return None

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
        log.debug('Slack message: "%s"' % message)
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

    async def send(self, text, to):
        payload = json.dumps({
            "id": 1,
            "type": "message",
            "channel": to,
            "text": text
        })
        log.debug('Sending payload: %s' % payload)
        if self._too_fast_warning:
            await asyncio.sleep(2)
            self._too_fast_warning = False
        await self.connection.write_message(payload)
        await asyncio.sleep(0.1)  # A small sleep here to allow Slack to respond

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

    async def send(self, text):
        # TODO: Help make this slack-specfic...
        await self.bot.send(text, self.info.get('id'))

    async def button_prompt(self, text, buttons):
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

        attachment = {
            "color": "#1E9E5E",
            "text": text,
            "actions": button_actions,
            "callback_id": str(id(self)),
            "fallback": text,
            "attachment_type": "default"
        }

        b = await self.bot.api('chat.postMessage', {
            'attachments': json.dumps([attachment]),
            'channel': self.info.get('id')})

        event = await self.bot.wait_for_event(type='message-action',
                                              callback_id=str(id(self)))
        action_value = MetaString(event['payload']['actions'][0]['value'])
        action_value._meta = {
            'event': event['payload']
        }

        attachment.pop('actions')  # Do not allow multiple button clicks.
        attachment['footer'] = '@{} selected "{}"'.format(event['payload']['user']['name'],
                                                          action_value)
        attachment['ts'] = time.time()

        await self.bot.api('chat.update', {
            'ts': b['ts'],
            'attachments': json.dumps([attachment]),
            'channel': self.info.get('id')})

        return action_value


class User(object):
    """Wrapper for a User with helpful functions."""

    def __init__(self, payload):
        assert type(payload) == dict
        self.__dict__ = payload
        self.__dict__.update(payload['profile'])

    def __unicode__(self):
        return self.id


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
        self.listening = None
        self.regex_groups = None
        self.regex_group_dict = {}

    def matches_regex(self, regex, save=True):
        """Check if this message matches the regex.

        If it does store the groups for later use.
        """
        if not self.text:
            return False

        # Choosing not to ignore case here.
        match = re.match(f"^{regex}$", self.text)
        if not match:
            return False

        if save:
            self.regex_groups = match.groups()
            self.regex_group_dict = match.groupdict()
        return True

    async def reply(self, text):
        """Reply to the original channel of the message."""
        # help hacks
        # help fix direct messages
        await self.bot.send(text, to=self.channel.info.get('id'))

    async def react(self, reaction):
        # TODO: self.bot.react(reaction, chat=self)
        await self.bot.api('reactions.add', {
            'name': reaction,
            'timestamp': self.raw.get('ts'),
            'channel': self.channel.info.get('id')})

    async def button_prompt(self, text, buttons):
        action = await self.channel.button_prompt(text, buttons)
        return action

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
            log.debug('Heard this from a wrong user.')
            return

        match = re.match(self.listening, new_message.text)
        if match:
            self.listening = None
            self.heard_message = new_message
            return
