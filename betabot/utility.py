"""
Utility functions
"""
from datetime import datetime, timedelta
import logging
from os import environ

LOG = logging.getLogger('utility')


def set_env_var(name: str, value: str) -> None:
    """
    Update an environment variable.
    """
    environ.update({name: value})


def get_env_var(name: str, fail_hard: bool = True) -> str:
    """
    Get an environment variable.

    If fail_hard, raise KeyError if var does not exist;
    else on non-existence, return empty string
    """
    try:
        return environ[name]
    except KeyError as e:
        message = f'{name} not set in the environment'
        if fail_hard:
            raise KeyError(message)
        else:
            LOG.debug(message)
            return ''


def get_slack_token() -> str:
    """
    Get SLACK_TOKEN from environment variable
    """
    return get_env_var('SLACK_TOKEN')


def get_signing_secret() -> str:
    """
    Get SLACK_SIGNING_SECRET from environment variable
    """
    return get_env_var('SLACK_SIGNING_SECRET')


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
