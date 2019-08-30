import time

import alphabot.bot

import logging

bot = alphabot.bot.get_instance()
log = logging.getLogger(__name__)

START_TIME = time.time()


def _make_help_text(help_list):
    reply = ''
    for usage, desc in help_list:
        if desc:
            reply += '`%s` - %s\n' % (usage, desc)
        else:
            reply += '`%s`\n' % usage
    return reply


@bot.add_command('!help$')
@bot.add_command('^help$', direct=True)
@bot.learn([
    'List your commands',
    'What can you do?',
    'What commands do you know?'])
async def generic_help(message):
    """Get summary of all commands

    Usage: !help
    """

    await message.reply('Here are my commands, but I can also understand natural language. '
                        'Just ask me "What can you do?"')
    help_text = _make_help_text(bot.help.list())
    await message.reply(help_text)


@bot.add_command('!help (.*)')
@bot.add_command('^help (.*)', direct=True)
async def help_query(message):
    """Get detailed help of a command

    Usage: !help <command>
    """
    query = message.regex_groups[0]
    help_text = _make_help_text(bot.help.list(query))
    await message.reply(help_text)


@bot.add_command('uptime', direct=True)
@bot.learn(["What's your uptime?", 'How long have you been running?'])
async def get_uptime(message):
    """Get amount of time this bot has been running

    Usage: uptime
    """

    runtime = int(time.time()) - int(START_TIME)

    if runtime < 60:
        await message.reply(f'{runtime} seconds')
        return

    runtime //= 60
    if runtime < 60:
        await message.reply(f'{runtime} minutes')
        return

    runtime //= 24
    if runtime < 24:
        await message.reply(f'{runtime} hours')
        return

    await message.reply(f'{runtime} days')
    return
