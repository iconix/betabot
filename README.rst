
Alphabot
---------
|pypi_download|_


==========================  =====
.. image:: images/logo.png  - Open source python bot to chat with `Slack <https://slack.com/>`_ and eventually other platforms like MS Teams.
                            - Alphabot is written for `Python 3 <https://www.python.org/>`_ leveraging ``asyncio`` library with ``async``/``await`` patterns.               
==========================  =====




Installation
============

Raw:

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
