import asyncio
import logging
import random

import betabot.bots.bot
from betabot.classes import Event

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()
log = logging.getLogger(__name__)


@bot.add_command('random number')
@bot.learn(
    ['Give me a random number',
     'roll the dice',
     'generatet a random number'])
async def random_number(event: Event):
    last_r = await bot.memory.get('random_number')
    r = random.randint(1, 10)
    await bot.memory.save('random_number', r)

    await event.reply("Random number is %s" % r)
    if last_r is not None:
        await asyncio.sleep(1)
        await event.reply("But last time I said it was %s" % last_r)
