import logging

import betabot.bots.bot
from betabot.classes import Event

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()
log = logging.getLogger(__name__)

@bot.add_command('button-example')
async def button_example(event: Event):
    action = await event.button_prompt(
        'Is this a good button example?',
        ['No', 'Yes'])

    await event.reply('Got "%s" from the button.' % action)
