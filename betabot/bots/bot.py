import importlib
from io import StringIO
import logging
from logging import Logger
import os
from pathlib import Path
import pkgutil
import re
import sys
import traceback
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slack_bolt.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.async_context import AsyncBoltContext
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.error import BoltUnhandledRequestError, BoltError
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_bolt.response import BoltResponse
from slack_sdk.web.async_client import AsyncWebClient
from textblob.classifiers import NaiveBayesClassifier
from tornado import web

from betabot import help
from betabot import memory
from betabot import utility
from betabot.classes.event import Event, EventActions, EventContext, EventData

# TODO: allow these logs with a -vv verbose arg
logging.getLogger('slack_sdk.web.async_slack_response').setLevel(logging.INFO)
logging.getLogger('asyncio').setLevel(logging.INFO)
logging.getLogger('slack_bolt.AsyncApp').setLevel(logging.INFO)

DEFAULT_SCRIPT_DIR = 'default-scripts'
DEBUG_CHANNEL = os.getenv('DEBUG_CHANNEL', 'betabot')

WEB_PORT = int(os.getenv('WEB_PORT', 8000))
WEB_NO_SSL = os.getenv('WEB_NO_SSL', '') != ''
WEB_PORT_SSL = int(os.getenv('WEB_PORT_SSL', 8443))

LOG = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
scheduler.start()


def get_instance(engine='cli', start_web_app=False) -> 'Bot':
    """Get a betabot instance.

    Args:
        engine (str): Type of betabot to create ('cli', 'slack')
        start_web_app (bool): Whether to start a web server with the engine.

    Returns:
        Bot: An betabot instance.
    """
    if not Bot.instance:
        engine_map = {
            'cli': 'BotCLI',
            'slack': 'BotSlack'
        }
        engine_class = engine_map.get(engine)

        if not engine_class:
            raise InvalidOptions(f'bot engine `{engine}` is not available')

        LOG.debug(f'creating a new bot instance. engine: {engine_class}')

        module_map = {
            'BotCLI': 'betabot.bots.botcli',
            'BotSlack': 'betabot.bots.botslack'
        }
        module = importlib.import_module(module_map.get(engine_class))
        engine_instance = getattr(module, engine_class)

        Bot.instance = engine_instance(start_web_app=start_web_app)

    return Bot.instance


class HealthCheck(web.RequestHandler):
    """An endpoint used to check if the app is up."""

    def data_received(self, chunk):
        pass

    def get(self):
        self.write('ok')


class Bot(object):
    instance: Optional['Bot'] = None

    def __init__(self, start_web_app=False):
        self.memory: memory.Memory = None
        self._on_start = []

        # TODO: self._bot_id?
        self._user_id = ''
        self._user = ''

        # TODO: support both channel id and name
        self._test_channel = utility.get_env_var('TEST_CHANNEL', '')

        self.help = help.Help()

        self._learn_map: List[Tuple[List[str], 'function']] = []  # saves all sentences to learn for a function
        self._classifier: NaiveBayesClassifier = None

        # this is a shortcut around implementing event listening across engines
        # should eventually cut this dependency on slack-bolt
        # TODO: subclass off of AsyncApp (and other bolt components) instead? or create an ABC
        self._bolt_app: Optional[AsyncApp] = None

        self._web_app = None
        if start_web_app:
            self._web_app = self._make_web_app()

    @staticmethod
    def _make_web_app():
        """Creates a web application.
        TODO: use aiohttp, or try FastAPI

        Returns:
            web.Application.
        """
        LOG.info('creating a web app')
        return web.Application([
            (r'/health', HealthCheck)
        ])

    async def setup(self, memory_type, script_paths):
        await self._setup_memory(memory_type=memory_type)
        await self._setup_scripts(script_paths)

    async def _setup_memory(self, memory_type='dict'):

        # TODO: memory module should provide this mapping.
        memory_map = {
            'dict': memory.MemoryDict,
            'redis': memory.MemoryRedis,
        }

        # get associated memory class or default to Dict memory type.
        memoryclass = memory_map.get(memory_type)
        if not memoryclass:
            raise InvalidOptions(
                'memory type "%s" is not available.' % memory_type)

        self.memory = memoryclass()
        await self.memory.setup()

    async def _setup_scripts(self, script_paths=None):
        # TODO: add a flag to control these
        default_path = Path(__file__).parents[1] / DEFAULT_SCRIPT_DIR
        LOG.info(f'loaded scripts: {self._import_scripts(str(default_path))}')

        if not script_paths:
            LOG.warning('no scripts specified for import')
        else:
            for path in script_paths:
                LOG.info(f'loaded scripts: {self._import_scripts(path)}')

    def _import_scripts(self, dirname) -> List[str]:
        LOG.info(f'importing scripts from {dirname}')
        if not isinstance(dirname, str):
            return []

        results = []
        for importer, pkg_name, _ in pkgutil.iter_modules([dirname]):
            LOG.debug(f'importing {pkg_name}')
            try:
                importer.find_module(pkg_name).load_module(pkg_name)
                results.append(pkg_name)
            except Exception as e:
                LOG.critical(f'could not load `{pkg_name}`. error follows.')
                LOG.critical(e, exc_info=1)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback_string = StringIO()
                traceback.print_exception(exc_type, exc_value, exc_traceback,
                                          file=traceback_string)

        return results

    async def start(self):
        if self._web_app:
            LOG.info('starting web app.')
            self._start_web_app()

        LOG.info('executing the start scripts.')
        for func in self._on_start:
            LOG.debug('on start: %s' % func.__name__)
            await func()

        @self._bolt_app.use
        async def log_incoming(logger: Logger, payload: Dict[str, Any], next: Callable[[], Awaitable[None]]):
            logger.info(f'{payload}')
            await next()  # pass control to the next middleware

        @self._bolt_app.use
        async def convert_app_mention(event: Optional[Dict[str, Any]], next: Callable[[], Awaitable[None]]):
            # to @bot messages
            if event.get('type') == 'app_mention':
                event['type'] = 'message'
            await next()

        @self._bolt_app.error
        async def on_error(logger: Logger, error: BoltError) -> BoltResponse:
            if isinstance(error, BoltUnhandledRequestError):
                logger.debug(error.current_response.__dict__)
                return BoltResponse(status=200, body='')
            else:
                # other error patterns
                return BoltResponse(status=500, body='something is wrong')

        LOG.info('bot started! listening to events.')

    def _start_web_app(self):
        """Creates a web server on WEB_PORT and WEB_PORT_SSL"""
        if not self._web_app:
            return
        LOG.info('listening on port %s' % WEB_PORT)
        self._web_app.listen(WEB_PORT)
        if not WEB_NO_SSL:
            try:
                self._web_app.listen(WEB_PORT_SSL, ssl_options={
                    "certfile": "/tmp/betabot.pem",  # generate these in your entrypoint
                    "keyfile": "/tmp/betabot.key"
                })
            except ValueError as e:
                LOG.warning(e)
                LOG.warning('failed to start SSL web app on %s. to disable - set WEB_NO_SSL',
                            WEB_PORT_SSL)

    def on_start(self, cmd):
        self._on_start.append(cmd)
        return cmd

    def on(self, event_type):
        """This decorator will invoke your function with the raw event."""

        if event_type == 'app_mention':
            raise ValueError('listening for raw event type `app_mention` is disallowed. Use bot.add_command(..., direct=True) instead.')

        def decorator(cmd):
            self.help.update(cmd, event_type)

            @self._bolt_app.event(event_type)
            async def on_ack(
                logger: Logger, client: AsyncWebClient, request: AsyncBoltRequest, response: BoltResponse,
                context: AsyncBoltContext, body: Dict[str, Any], payload: Dict[str, Any],
                options: Optional[Dict[str, Any]], shortcut: Optional[Dict[str, Any]], action: Optional[Dict[str, Any]],
                view: Optional[Dict[str, Any]], command: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]],
                message: Optional[Dict[str, Any]], ack: AsyncAck, say: AsyncSay, respond: AsyncRespond,
                next: Callable[[], Awaitable[None]]
            ):
                '''
                function signature derived from bolt's AsyncArgs:
                https://github.com/slackapi/bolt-python/blob/8babac6c69e2ec2f5c7a24d9785438b80b4962c7/slack_bolt/kwargs_injection/async_args.py
                '''
                if utility.event_is_too_old(request.body.get('event_time', utility.get_timestamp()), request.body.get('event_id')):
                    return

                # TODO: create a script interface based on Chat/Message/Event
                event_actions = EventActions(ack=ack, say=say, respond=respond, next=next)
                event_context = EventContext(client=client, request=request, response=response, context=context, bot=self)
                event_data = EventData(body=body, payload=payload, options=options, shortcut=shortcut, action=action,
                    view=view, command=command, event=event, message=message)

                event = Event(actions=event_actions, context=event_context, data=event_data)

                await cmd(event)

            return on_ack

        return decorator

    def add_command(self, regex: Union[re.Pattern, str], direct=False):
        """This decorator will invoke your function with a message that matches the pattern."""

        # TODO: check if script uses `regex` library instead of `re` (not supported by bolt at the moment)
        if isinstance(regex, str):
            regex = re.compile(regex)

        def decorator(cmd):
            # register some basic help using the regex
            self.help.update(cmd, regex)

            @self._bolt_app.message(regex)
            async def command_ack(
                client: AsyncWebClient, request: AsyncBoltRequest, response: BoltResponse,
                context: AsyncBoltContext, body: Dict[str, Any], payload: Dict[str, Any],
                options: Optional[Dict[str, Any]], shortcut: Optional[Dict[str, Any]], action: Optional[Dict[str, Any]],
                view: Optional[Dict[str, Any]], command: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]],
                message: Optional[Dict[str, Any]], ack: AsyncAck, say: AsyncSay, respond: AsyncRespond,
                next: Callable[[], Awaitable[None]]
            ):
                '''
                function signature derived from bolt's AsyncArgs:
                https://github.com/slackapi/bolt-python/blob/8babac6c69e2ec2f5c7a24d9785438b80b4962c7/slack_bolt/kwargs_injection/async_args.py
                '''
                if utility.event_is_too_old(request.body.get('event_time', utility.get_timestamp()), request.body.get('event_id')):
                    return

                # TODO: create a script interface based on Chat/Message/Event
                event_actions = EventActions(ack=ack, say=say, respond=respond, next=next)
                event_context = EventContext(client=client, request=request, response=response, context=context, bot=self)
                event_data = EventData(body=body, payload=payload, options=options, shortcut=shortcut, action=action,
                    view=view, command=command, event=event, message=message)

                event = Event(actions=event_actions, context=event_context, data=event_data)
                found_match = event.match_regex(regex)

                if found_match and (not direct or event.is_direct):
                    await cmd(event)

            return command_ack

        return decorator

    def learn(self, sentences: List[str], direct=False):
        """Learn sentences for a command.
        :param sentences: list of strings -
        :param direct:
        :return:
        """

        def decorator(cmd):
            self._learn_map.append((sentences, cmd))
            return cmd

        return decorator

    def add_help(self, desc=None, usage=None, tags=None):
        def decorator(cmd):
            self.help.update(cmd, usage=usage, desc=desc, tags=tags)
            return cmd

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
            # default is every second. We don't want that.
            schedule_keywords['second'] = '0'

        def decorator(cmd):
            LOG.info('new schedule: cron[%s] => %s()' % (schedule_keywords,
                                                         cmd.__name__))

            scheduler.add_job(cmd, trigger='cron', **schedule_keywords)
            return cmd

        return decorator

    # functions that scripts can tell bot to execute.

    async def event_to_chat(self, event) -> 'Chat':
        raise CoreException('Chat engine "%s" is missing event_to_chat(...)' % (
            self.__class__.__name__))

    async def api(self, text, to):
        raise CoreException('Chat engine "%s" is missing api(...)' % (
            self.__class__.__name__))

    async def send(self, text, to, extra=None) -> 'Chat':
        raise CoreException('Chat engine "%s" is missing send(...)' % (
            self.__class__.__name__))

    async def _update_channels(self):
        raise CoreException('Chat engine "%s" is missing _update_channels(...)' % (
            self.__class__.__name__))

    def get_channel(self, name) -> 'Channel':
        raise CoreException('Chat engine "%s" is missing get_channel(...)' % (
            self.__class__.__name__))

    def find_channels(self, pattern):
        raise CoreException('Chat engine "%s" is missing find_channels(...)' % (
            self.__class__.__name__))


class betabotException(Exception):
    """Top of hierarchy for all betabot failures."""


class CoreException(betabotException):
    """Used to signify a failure in the robot's core."""


class InvalidOptions(betabotException):
    """Robot failed because input options were somehow broken."""


class WebApplicationNotAvailable(betabotException):
    """Failed to register web handler because no web app registered."""


def handle_exceptions(future, chat):
    """Attach to Futures that are not yielded."""

    if not hasattr(future, 'add_done_callback'):
        LOG.error('Could not attach callback. Exceptions will be missed.')
        return

    def cb(cbfuture):
        """Custom callback which is chat aware."""
        try:
            cbfuture.result()
        except betabotException as e:
            """This exception was raised intentionally. No need for traceback."""
            if chat:
                chat.reply('Script had an error: %s' % e)
            else:
                LOG.error('Script had an error: %s' % e)
        except Exception as e:
            LOG.critical('Script had an error: %s' % e, exc_info=1)

            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_string = StringIO()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      file=traceback_string)

            if chat:
                chat.reply('Script had an error: %s ```%s```' % (e, traceback_string.getvalue()))

    # tornado functionality to add a custom callback
    future.add_done_callback(cb)


def dict_subset(big: dict, small: dict) -> bool:
    return small.items() <= big.items()  # python 3
