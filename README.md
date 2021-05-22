# Betabot
![pypi_download][]

<table>
<tbody>
<tr class="odd">
<td><p><img src="images/logo.png" alt="image" /></p></td>
<td><ul>
<li>Open source Python bot to chat with Slack.</li>
<li>Betabot is written for <a href="https://www.python.org/">Python 3</a> leveraging the <a href="https://github.com/slackapi/bolt-python"><code>Slack Bolt</code></a> bot framework.</li>
</ul></td>
</tr>
</tbody>
</table>

## Installation

```bash
git clone https://github.com/iconix/betabot.git
cd betabot
python3 -m venv .betabot
source .betabot/bin/activate
pip install -e .
```

## Example

Betabot has some support for conversation flow:

# Slack

![image][]

# CLI

```diff
λ betabot -S betabot/sample-scripts/
betabot> hi
! betabot:  Hi! How are you?
betabot> great!
! betabot:  great!? Me too!
betabot> uptime
betabot> @betabot uptime
! betabot:  13 seconds
```

## Running the bot

If you installed betabot as a python package then simply run it:

```bash
betabot -S betabot/sample-scripts/  # or...
betabot -S path/to/your/scripts/
```

```bash
export SLACK_TOKEN=xoxb-YourToken
betabot --engine slack -S path/to your/scripts/
```

# API

Function decorators

## on_start

```python
@bot.on_start()
def some_command():
    # This command will execute whenever a bot starts
```

## on

Generic event matcher. Useful for things that aren't chat-initiated,
like people joining a room, emoji events, etc...

This command will get executed when an event is received with key `type` and value `"something"`

```python
@bot.on(type="something")
def some_command(event: dict):
    # event contents depend on the event. For slack - https://api.slack.com/events-api#receiving_events
    log.debug(event)
```

## add_command

Most common decorator - executes when the listener sees the regex. If `direct` is set to True then this will only
trigger if the message is sent in a DM or if the message begins with
@\<bot name\>

```python
@bot.add_command('regex here', direct=False)
def normal_command(message: Chat):
    await message.reply('Regex was matched!')
```

## learn

WIP - Uses `NaiveBayesClassifier` to do some primitive language learning.

```python
@bot.learn(['Print seven', 'What is your lucky number', 'Give me a number between six and eight'])
def text_match_command(message: Chat):
    await message.reply('Seven!')
```

## on_schedule

WIP

    year (int|str) - 4-digit year
    month (int|str) - month (1-12)
    day (int|str) - day of the (1-31)
    week (int|str) - ISO week (1-53)
    day_of_week (int|str) - number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun)
    hour (int|str) - hour (0-23)
    minute (int|str) - minute (0-59)
    second (int|str) - second (0-59)
    start_date (datetime|str) - earliest possible date/time to trigger on (inclusive)
    end_date (datetime|str) - latest possible date/time to trigger on (inclusive)
    timezone (datetime.tzinfo|str) - time zone to use for the date/time calculations
    (defaults to scheduler timezone)

```python
@bot.on_schedule(minute=0)
def on_the_hour():
    channel = bot.get_channel(name='hourly')
    await channel.send('The time has come!')
```

Bot functions

## api

```python
bot.api(method: str, params: dict)
```

## send

```python
bot.send(text, to, extra)
```

## get_channel

```python
bot.get_channel(**kwargs)
```

  [pypi_download]: https://badge.fury.io/py/alphabot.png
  [image]: images/example.png
