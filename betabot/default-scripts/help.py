import betabot.bots.bot
from betabot.classes import Event

bot = betabot.bots.bot.get_instance()


def _make_help_text(help_list):
    reply = ''
    for usage, desc in help_list:
        if desc:
            reply += '`%s` - %s\n' % (usage, desc)
        else:
            reply += '`%s`\n' % usage
    return reply


#@bot.add_command('!help', direct=True) TODO: make work in DMs
@bot.add_command('help$', direct=True)
@bot.learn([
    'List your commands',
    'What can you do?',
    'What commands do you know?'])
async def generic_help(event: Event, **kwargs):
    """get summary of all commands

    Usage: help
    """
    await event.actions.say('Here are my commands, but I can also understand natural language. '
                            'Just ask me "What can you do?"')
    help_text = _make_help_text(bot.help.list())
    await event.actions.say(help_text)


#@bot.add_command('!help (.*)', direct=True)
@bot.add_command('help (.*)', direct=True)
async def help_query(event: Event, **kwargs):
    """get detailed help of a command

    Usage: help <command>
    """
    query = event.regex_groups[0]
    help_text = _make_help_text(bot.help.list(query))
    await event.actions.say(help_text)
