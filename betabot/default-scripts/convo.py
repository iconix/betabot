import logging

import betabot.bots.bot
from betabot.classes import Event

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()
log = logging.getLogger(__name__)


# TODO: make this work in DMs and app_mention threads
# @bot.add_command('hi')
# async def conversation(message, **kwargs):
#     log.debug('starting a conversation')
#     await message.reply("Hi! How are you?")

#     response = await message.listen_for('(.*)')

#     await message.reply("%s? Me too!" % response.text)

# @bot.add_command('talk to me', direct=True)
# async def conversation(event: Event):
#     log.debug('starting a conversation')
#     # TODO: respond to thread
#     resp = await event.actions.say('hi! how are you?')

#     # TODO: listen to replies in same thread (message_replied subtype?)
