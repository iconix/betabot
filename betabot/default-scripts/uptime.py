import time

import betabot.bots.bot
from betabot.classes import Event


BOT = betabot.bots.bot.get_instance()

START_TIME = time.time()


@BOT.add_command('uptime', direct=True)
@BOT.learn(["What's your uptime?", 'How long have you been running?'])
async def get_uptime(event: Event):
    """get amount of time this bot has been running

    (bitwise pluralization trick: https://stackoverflow.com/a/65063284)

    Usage: uptime
    """

    say = event.actions.say
    runtime = int(time.time()) - int(START_TIME)

    if runtime < 60:
        await say(**{
            'text': f'`{runtime} second{"s"[:runtime^1]}`',
            'channel': event.channel,
            'thread_ts': event.ts
        })
        return

    runtime //= 60
    if runtime < 60:
        await say(**{
            'text': f'`{runtime} minute{"s"[:runtime^1]}`',
            'channel': event.channel,
            'thread_ts': event.ts
        })
        return

    runtime //= 60
    if runtime < 24:
        await say(**{
            'text': f'`{runtime} hour{"s"[:runtime^1]}`',
            'channel': event.channel,
            'thread_ts': event.ts
        })
        return

    runtime //= 24
    await say(**{
        'text': f'`{runtime} day{"s"[:runtime^1]}`',
        'channel': event.channel,
        'thread_ts': event.ts
    })
