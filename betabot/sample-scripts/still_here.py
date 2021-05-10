import betabot.bots.bot

# Actual bot instance. Will be available because this file should only be
# invoked inside of a script-discovery code of the bot itself!
bot = betabot.bots.bot.get_instance()


@bot.on_schedule(minute='0')
async def still_here():
    channel = bot.get_channel(name='betabot-debug')
    if channel:
        await channel.send('I am still here!')
