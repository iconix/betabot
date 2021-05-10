"""
Utility functions
"""
from datetime import datetime, timedelta
import logging
from os import environ
from typing import Optional

LOG = logging.getLogger(__name__)
EVENT_EXPIRY_IN_SECONDS = 5


def set_env_var(name: str, value: str) -> None:
    """
    Update an environment variable.
    """
    environ.update({name: value})


def get_env_var(name: str, default: Optional[str] = None) -> str:
    """
    Get an environment variable.

    If var does not exist but a default is provided, return it;
    otherwise, raise KeyError.
    """
    try:
        return environ[name]
    except KeyError:
        message = f'{name} not set in the environment'
        if default is None:
            raise KeyError(f'{message}; no default provided')
        else:
            LOG.info(f'{message}; using default value {default}')
            return default


def get_app_token() -> str:
    """
    Get SLACK_APP_TOKEN from environment variable
    """
    return get_env_var('SLACK_APP_TOKEN')


def get_bot_token() -> str:
    """
    Get SLACK_BOT_TOKEN from environment variable
    """
    return get_env_var('SLACK_BOT_TOKEN')


def get_weekday(dt: datetime = datetime.today()) -> str:
    """
    Get the day of the week of a datetime
    """
    # TODO: timezones, probably
    return dt.strftime('%A')


def add_hours_from(hours: int, dt: datetime = datetime.today()) -> str:
    """
    Add hours to the hour of day of a specfied datetime
    """
    return '{d:%l} {d:%p}'.format(d=datetime.today() + timedelta(hours=hours)).strip()


def get_timestamp(dt: datetime = datetime.today()) -> float:
    return dt.timestamp()


def event_is_too_old(event_time: float, event_id: str) -> bool:
    """
    Check if an event happened too long ago.

    This is needed because the SlackEventAdapter seems to receive old events sometimes,
    either as repeats or on delay because the bot server wasn't running (?)

    # TODO: timezones, probably (server vs local)
    """
    seconds_ago = get_timestamp() - event_time
    too_old = seconds_ago > EVENT_EXPIRY_IN_SECONDS

    if too_old:
        LOG.warning(f'received an old event {event_id} (from ~{seconds_ago:.2f} seconds ago; expiry is {EVENT_EXPIRY_IN_SECONDS}s)')

    return too_old
