import argparse
import asyncio
import logging
import os
import signal

import requests

import betabot.bots.bot
from betabot.version import __version__

requests.packages.urllib3.disable_warnings()

LOG = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description='betabot')
parser.add_argument('-v', '--version', help='Show version and exit', dest='version',
                    action='store_true', default=False)
parser.add_argument('-S', '--scripts', dest='scripts', metavar='dir',
                    action='store', default=[], nargs='+',
                    help=('Directory to fetch bot scripts. '
                          'Can be specified multiple times'))
parser.add_argument('-e', '--engine', dest='engine', action='store',
                    default='cli', help='What chat engine to use. Slack or cli')
parser.add_argument('-m', '--memory', dest='memory', action='store',
                    default='dict', help='What persistent storage to use.')

# n.b., if --no-web-app is present, start_web_app is False
parser.add_argument('--no-web-app', dest='start_web_app', action='store_false',
                    default=True, help='Do not run the web server.')

args = parser.parse_args()


async def start_betabot():
    if args.version:
        LOG.info(f"version {__version__}")
        exit()

    bot = betabot.bots.bot.get_instance(engine=args.engine, start_web_app=args.start_web_app)
    memory = args.memory

    full_path_scripts = [os.path.abspath(s) for s in args.scripts]
    LOG.debug('full path scripts: %s' % full_path_scripts)
    await bot.setup(memory_type=memory, script_paths=full_path_scripts)
    await bot.start()


def start_ioloop():
    try:
        level_msg = f'log level is {logging.getLevelName(LOG.getEffectiveLevel())}'
        if LOG.getEffectiveLevel() > logging.INFO:
            print(level_msg)
        else:
            LOG.info(level_msg)

        LOG.info('starting ioloop')
        loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_debug(LOG.getEffectiveLevel() == logging.DEBUG)

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _terminate)

        loop.run_until_complete(start_betabot())
    except betabot.bots.bot.betabotException as e:
        LOG.critical('betabot failed. Reason: %s' % e)


def _terminate():
    print()
    LOG.info('ctrl-c caught, shutting down')

    for task in asyncio.all_tasks():
        task.cancel()
    asyncio.ensure_future(exit())


if __name__ == '__main__':
    start_ioloop()
