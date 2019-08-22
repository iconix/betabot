import logging

import alphabot.bot

bot = alphabot.bot.get_instance()
log = logging.getLogger(__name__)


@bot.add_command('!help$')
@bot.learn([
    'List your commands',
    'What can you do?',
    'What commands do you know?',
    'help'])
async def help(message):
    """Get summary of all commands

    Usage: !help
    """
    help_text = _make_help_text(bot.help.list())
    await message.reply(help_text)


@bot.add_command('!help (.*)')
async def help_query(message):
    """Get detailed help of a command

    Usage: !help <command>
    """
    query = message.regex_groups[0]
    help_text = _make_help_text(bot.help.list(query))
    await message.reply(help_text)


def _make_help_text(help_list):
    reply = ''
    for usage, desc in help_list:
        if desc:
            reply += '`%s` - %s\n' % (usage, desc)
        else:
            reply += '`%s`\n' % usage
    return reply
