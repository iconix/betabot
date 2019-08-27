
Alphabot
---------
|pypi_download|_


==========================  =====
.. image:: images/logo.png  - Open source python bot to chat with `Slack <https://slack.com/>`_ and eventually other platforms like MS Teams.
                            - Alphabot is written for `Python 3 <https://www.python.org/>`_ leveraging ``asyncio`` library with ``async``/``await`` patterns.               
==========================  =====




Installation
============

.. code-block:: bash

    git clone https://github.com/mikhail/alphabot.git
    cd alphabot
    pip install -e .
    
Example
=======
Alphabot is optimized for conversation flow:

.. image:: images/example.png


Running the bot
===============

If you installed alphabot as a python package then simply run it:

.. code-block:: bash

    alphabot -S alphabot/sample-scripts/  # or...
    alphabot -S path/to/your/scripts/

.. code-block:: bash

    export SLACK_TOKEN=xoxb-YourToken
    alphabot --engine slack -S path/to your/scripts/


.. |pypi_download| image:: https://badge.fury.io/py/alphabot.png
.. _pypi_download: https://pypi.python.org/pypi/alphabot


API
---

Function decorators

on_start
====

.. code-block:: python

    @bot.on_start()
    def some_command():
        # This command will execute whenever a bot starts
        
on
====

Generic event matcher. Useful for things that aren't chat-initiated, like people joining a room, emoji events, etc...

This command will get executed when an event is received with key `type` and value `"something"`

.. code-block:: python

    @bot.on(type="something")
    def some_command(event: dict):
        # event contents depend on the event. For slack - https://api.slack.com/events-api#receiving_events
        log.debug(event)
        
add_command
====

Most common decorator - executes when the listener sees the regex. If `direct` is set to True then this will only trigger if the message is sent in a DM or if the message begins with @<bot name>

.. code-block:: python

    @bot.add_command('regex here', direct=False)
    def normal_command(message: Chat):
        await message.reply('Regex was matched!')
        
learn
====

WIP - Uses `NaiveBayesClassifier` to do some primitive language learning.

.. code-block:: python

    @bot.learn(['Print seven', 'What is your lucky number', 'Give me a number between six and eight'])
    def text_match_command(message: Chat):
        await message.reply('Seven!')


on_schedule
====
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

.. code-block:: python

    @bot.on_schedule(minute=0)
    def on_the_hour():
        channel = bot.get_channel(name='hourly')
        await channel.send('The time has come!')

Bot functions

api
====

.. code-block:: python

    bot.api(method: str, params: dict)
    
    
send
====

.. code-block:: python

    bot.send(text, to, extra)
    
get_channel
====

.. code-block:: python

    bot.get_channel(**kwargs)
