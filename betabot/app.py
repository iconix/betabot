#!/usr/bin/env python
import argparse
import asyncio
import logging
import os
import signal

import requests

import betabot.bots.bot

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

# NOTE: Since the variable is start_web_app, it does actually default True.
parser.add_argument('--no-web-app', dest='start_web_app', action='store_false',
                    default=True, help='Do not run the web server.')

args = parser.parse_args()

__author__ = ('Nadja Rhodes <narhodes1+blog@gmail.com>',)
__version__ = '0.0.1'


async def start_betabot():
    if args.version:
        print(__version__)
        exit()

    bot = betabot.bots.bot.get_instance(engine=args.engine, start_web_app=args.start_web_app)
    memory = args.memory

    full_path_scripts = [os.path.abspath(s) for s in args.scripts]
    LOG.debug('full path scripts: %s' % full_path_scripts)
    await bot.setup(memory_type=memory, script_paths=full_path_scripts)
    await bot.start()


def start_ioloop():
    try:
        loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_debug('DEBUG')

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _ask_exit)

        loop.run_until_complete(start_betabot())
    except betabot.bots.bot.betabotException as e:
        LOG.critical('betabot failed. Reason: %s' % e)


def _ask_exit():
    print()
    LOG.info('CTRL-C Caught, shutting down')

    for task in asyncio.Task.all_tasks():
        task.cancel()
    asyncio.ensure_future(exit())


if __name__ == '__main__':
    start_ioloop()
