import logging

import betabot.bots.bot
from betabot.classes import Event

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()
log = logging.getLogger(__name__)


@bot.on(type='message', message='acknowledge')
async def acknowledge(event: Event):
    message = bot.event_to_chat(event)
    await message.reply('Tadaa!')
    log.debug('Attached to a message!')
