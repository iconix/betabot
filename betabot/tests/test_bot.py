import asyncio
import logging

import aiounittest
from aiounittest import mock

from betabot import bot as AB
from betabot.tests.helper import mock_tornado

log = logging.getLogger(__name__)


class TestException(Exception):
    """Unique exception to be used during testing."""


class TestWebApp(aiounittest.AsyncTestCase):
    def get_app(self):
        bot = AB.get_instance(start_web_app=True)
        return bot.make_web_app()

    async def _test_healthz(self):
        response = self.fetch('/health_check')
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode(), 'ok')


class TestBot(aiounittest.AsyncTestCase):

    async def test_get_instance(self):
        bot = AB.get_instance()
        bot2 = AB.get_instance()

        assert (id(bot) == id(bot2))

    async def test_setup(self):
        bot = AB.Bot()
        bot._setup_memory = mock_tornado()
        bot._setup = mock_tornado()
        bot._gather_scripts = mock_tornado()
        await bot.setup('unit-memory', 'unit-scripts')

        self.assertEqual(bot._setup_memory.call_count, 1)

    def test_check_event_kwargs(self):
        bot = AB.Bot()
        event = {'test': 'test', 'foobar': ['one', 'two']}
        kwargs = {'test': 'test', 'foobar': ['one', 'two']}
        self.assertTrue(bot._check_event_kwargs(event, kwargs))

        event = {'type': 'message', 'message': 'Hello!'}
        kwargs = {'type': 'message'}
        self.assertTrue(bot._check_event_kwargs(event, kwargs))

        event = {'test': 'test', 'foobar': ['one', 'two'], 'extra': 'yes'}
        kwargs = {'test': 'test', 'foobar': ['one', 'two']}
        self.assertTrue(bot._check_event_kwargs(event, kwargs))

        event = {'test': 'test'}
        kwargs = {'test': 'test', 'foobar': ['one', 'two']}
        self.assertFalse(bot._check_event_kwargs(event, kwargs))

    async def _test_wait_event(self):
        bot = AB.Bot()
        test_event = {'unittest': True}
        waiter = bot.wait_for_event(**test_event)
        bot.event_to_chat = mock.AsyncMockIterator(seq=[test_event])
        bot._get_next_event = mock_tornado(
            side_effect=[asyncio.ensure_future(test_event), TestException])
        try:
            await bot.start()
        except TestException:
            pass

        event = await waiter
        self.assertEquals(event, test_event)
