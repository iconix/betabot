import importlib
from io import StringIO
import logging
import os
import pkgutil
import sys
import traceback
from typing import List, Tuple

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from textblob.classifiers import NaiveBayesClassifier
from tornado import web

from betabot import help
from betabot import memory

DEFAULT_SCRIPT_DIR = 'default-scripts'
DEBUG_CHANNEL = os.getenv('DEBUG_CHANNEL', 'betabot')

WEB_PORT = int(os.getenv('WEB_PORT', 8000))
WEB_NO_SSL = os.getenv('WEB_NO_SSL', '') != ''
WEB_PORT_SSL = int(os.getenv('WEB_PORT_SSL', 8443))

LOG = logging.getLogger(__name__)
log_level = logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
LOG.setLevel(log_level)

scheduler = AsyncIOScheduler()
scheduler.start()


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

    # Tornado functionality to add a custom callback
    future.add_done_callback(cb)


def dict_subset(big: dict, small: dict) -> bool:
    return small.items() <= big.items()  # Python 3


class HealthCheck(web.RequestHandler):
    """An endpoint used to check if the app is up."""

    def data_received(self, chunk):
        pass

    def get(self):
        self.write('ok')


class Bot(object):
    instance = None
    engine = 'default'

    def __init__(self, start_web_app=False):
        self.module_path = ''
        self.memory: memory.Memory = None
        self.event_listeners = []
        self._web_events = []
        self._on_start = []

        self._user_id = ''
        self._user_name = ''

        self.help = help.Help()

        self._learn_map: List[Tuple[List[str], 'function']] = []  # saves all sentences to learn for a function
        self._classifier: NaiveBayesClassifier = None

        self._web_app = None
        if start_web_app:
            self._web_app = self.make_web_app()

    @staticmethod
    def make_web_app():
        """Creates a web application.

        Returns:
            web.Application.
        """
        LOG.info('Creating a web app')
        return web.Application([
            (r'/health_check', HealthCheck)
        ])

    def _start_web_app(self):
        """Creates a web server on WEB_PORT and WEB_PORT_SSL"""
        if not self._web_app:
            return
        LOG.info('Listing on port %s' % WEB_PORT)
        self._web_app.listen(WEB_PORT)
        if not WEB_NO_SSL:
            try:
                self._web_app.listen(WEB_PORT_SSL, ssl_options={
                    "certfile": "/tmp/betabot.pem",  # Generate these in your entrypoint
                    "keyfile": "/tmp/betabot.key"
                })
            except ValueError as e:
                LOG.error(e)
                LOG.error('Failed to start SSL web app on %s. To disable - set WEB_NO_SSL',
                          WEB_PORT_SSL)

    def _setup(self):
        pass

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
        memoryclass = memory_map.get(memory_type)
        if not memoryclass:
            raise InvalidOptions(
                'Memory type "%s" is not available.' % memory_type)

        self.memory = memoryclass()
        await self.memory.setup()

    def load_all_modules_from_dir(self, dirname):
        LOG.debug('Loading modules from "%s"' % dirname)
        for importer, package_name, _ in pkgutil.iter_modules([dirname]):
            self.module_path = "%s/%s" % (dirname, package_name)
            LOG.debug("Importing '%s'" % package_name)
            try:
                importer.find_module(package_name).load_module(package_name)
            except Exception as e:
                LOG.critical('Could not load `%s`. Error follows.' % package_name)
                LOG.critical(e, exc_info=1)
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

    async def _gather_scripts(self, script_paths=None):
        LOG.info('Gathering scripts...')

        if not script_paths:
            LOG.warning('Warning! You did not specify any scripts to load.')
        else:
            for path in script_paths:
                LOG.info('Gathering functions from %s' % path)
                self.load_all_modules_from_dir(path)

        # TODO: Add a flag to control these
        LOG.info('Installing default scripts...')
        pwd = os.path.dirname(os.path.realpath(__file__))
        self.load_all_modules_from_dir(
            "{path}/../{default}".format(path=pwd, default=DEFAULT_SCRIPT_DIR))

    def _event(self, payload):
        LOG.info('Adding an event on top of the stack: %s' % payload)
        self._web_events.append(payload)

    async def _get_next_event(self):
        pass

    async def start(self):
        if self._web_app:
            LOG.info('Starting web app.')
            self._start_web_app()

        LOG.info('Executing the start scripts.')
        for func in self._on_start:
            LOG.debug('On Start: %s' % func.__name__)
            await func()

        LOG.info('Bot started! Listening to events.')

        while True:
            event = await self._get_next_event()

            LOG.debug('Received event: %s' % event)
            LOG.debug('Checking against %s listeners' % len(self.event_listeners))

            if event['text']:
                if not self._classifier:
                    learn_map = []
                    for l in self._learn_map:
                        learn_map.extend([(k, l[1]) for k in l[0]])
                    self._classifier = NaiveBayesClassifier(learn_map)

                choices = self._classifier.prob_classify(event['text'])
                func = choices.max()
                prob = choices.prob(func)
                LOG.debug(f'NLTK matched `{func.__name__}` function at {int(prob * 100)}%')
                message = await self.event_to_chat(event)
                min_prob = 0.65 if message.is_direct else 0.95
                if prob > min_prob:
                    asyncio.ensure_future(func(message))
                    continue  # Do not loop through event listeners!

            # Note: Copying the event_listeners list here to prevent
            # mid-loop modification of the list.
            for kwargs, func in list(self.event_listeners):
                match = self._check_event_kwargs(event, kwargs)
                LOG.debug('Function %s requires %s. Match: %s' % (
                    func.__name__, kwargs, match))
                if match:
                    future = func(event=event)
                    asyncio.ensure_future(future)
                    # TODO: add a way to detect if any of these were "REAL" Match
                    #       then execute the NLP part if none matched.

    async def wait_for_event(self, **event_args):
        # Demented python scope.
        # http://stackoverflow.com/questions/4851463/python-closure-write-to-variable-in-parent-scope
        # This variable could be an object, but instead it's a single-element list.
        event_matched = []

        async def mark_true(event):
            event_matched.append(event)

        LOG.info('Creating a temporary listener for %s' % (event_args,))
        self.event_listeners.append((event_args, mark_true))

        while not event_matched:
            await asyncio.sleep(0.001)

        LOG.info('Deleting the temporary listener for %s' % (event_args,))
        self.event_listeners.remove((event_args, mark_true))

        return event_matched[0]

    def add_listener(self, chat, **kwargs):
        LOG.debug('Adding chat listener...')

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
        for kw, cmd in self.event_listeners:
            if (hasattr(cmd, '_listener_chat_id') and
                    cmd._listener_chat_id == id(chat)):
                match = (kw, cmd)
        self.event_listeners.remove(match)

    def _check_event_kwargs(self, event, kwargs):
        """Check that all expected kwargs were satisfied by the event."""
        return dict_subset(event, kwargs)

    # Decorators to be used in development of scripts

    def on_start(self, cmd):
        self._on_start.append(cmd)
        return cmd

    def _register_function(self, kwargs, cmd):
        LOG.debug('New Listener: %s => %s()' % (kwargs, cmd.__name__))
        self.event_listeners.append((kwargs, cmd))

    def on(self, **kwargs):
        """This decorator will invoke your function with the raw event."""

        def decorator(cmd):
            self._register_function(kwargs, cmd)
            return cmd

        return decorator

    def add_command(self, regex, direct=False):
        """Will convert the raw event into a message object for your function."""

        def decorator(cmd):
            # Register some basic help using the regex.
            self.help.update(cmd, regex)

            async def wrapper(event):
                message = await self.event_to_chat(event)
                matches_regex = message.matches_regex(regex)
                LOG.debug('Command %s should match the regex %s' % (cmd.__name__, regex))
                if not matches_regex:
                    return False

                if direct and not message.is_direct:
                    return False

                LOG.debug(f"Executing {cmd.__name__}")

                await cmd(message=message, **message.regex_group_dict)
                return True

            wrapper.__name__ = 'wrapped:%s' % cmd.__name__

            self._register_function({'type': 'message'}, wrapper)
            return cmd

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
            # Default is every second. We don't want that.
            schedule_keywords['second'] = '0'

        def decorator(cmd):
            LOG.info('New Schedule: cron[%s] => %s()' % (schedule_keywords,
                                                         cmd.__name__))

            scheduler.add_job(cmd, trigger='cron', **schedule_keywords)
            return cmd

        return decorator

    # Functions that scripts can tell bot to execute.

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


def get_instance(engine='cli', start_web_app=False) -> Bot:
    """Get an betabot instance.

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
            raise InvalidOptions('Bot engine "%s" is not available.' % engine)

        LOG.debug('Creating a new bot instance. engine: %s' % engine_class)

        module_map = {
            'BotCLI': 'betabot.bots.botcli',
            'BotSlack': 'betabot.bots.botslack'
        }
        module = importlib.import_module(module_map.get(engine_class))
        engine_instance = getattr(module, engine_class)

        Bot.instance = engine_instance(start_web_app=start_web_app)

    return Bot.instance
