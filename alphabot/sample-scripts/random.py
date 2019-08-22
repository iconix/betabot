import asyncio
import logging
import random

import alphabot.bot

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = alphabot.bot.get_instance()
log = logging.getLogger(__name__)


@bot.on_schedule(minute='0')
async def still_here():
    channel = bot.get_channel(name='alphabot-debug')
    if channel:
        await channel.send('I am still here!')


@bot.add_command('button-example')
async def button_example(message):
    action = await message.button_prompt(
        'Is this a good button example?',
        ['No', 'Yes'])

    await message.reply('Got "%s" from the button.' % action)


@bot.on(type='message', message='acknowledge')
async def acknowledge(event):
    message = bot.event_to_chat(event)
    await message.reply('Tadaa!')
    log.info('Attached to a message!')


@bot.add_command('lunch')
async def lunch_suggestion(message):
    await message.reply("How about Chipotle?")

    if bot.engine == 'slack':
        await message.react('burrito')


@bot.add_command('hi')
async def conversation(message):
    log.info('Starting a conversation')
    await message.reply("How are you?")

    response = await message.listen_for('(.*)')

    await message.reply("%s? Me too!" % response.text)


@bot.add_command('random number')
@bot.learn(
    ['Give me a random number',
     'roll the dice',
     'generatet a random number'])
async def random_number(message):
    last_r = await bot.memory.get('random_number')
    r = random.randint(1, 10)
    await bot.memory.save('random_number', r)

    await message.reply("Random number is %s" % r)
    if last_r is not None:
        await asyncio.sleep(1)
        await message.reply("But last time I said it was %s" % last_r)
