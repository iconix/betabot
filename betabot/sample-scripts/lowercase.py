import logging

import betabot.bots.bot
from betabot.classes import Event

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()
log = logging.getLogger(__name__)


@bot.add_command('lowercase?')
async def conversation(event: Event):
    await event.actions.say('til i die')
