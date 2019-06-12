import json
import logging
import os

import redis

log = logging.getLogger(__name__)


class Memory(object):
    """Memory interface to Alphabot."""

    async def save(self, key, value):
        # TODO: Add checks / hashing to prevent bad keys from breaking
        await self._save(key, value)

    async def get(self, key, default=None):
        value = await self._get(key, default)
        return value

    async def setup(self):
        await self._setup()

    async def _setup(self):
        log.debug('Memory engine %s does not require any setup.' % (
            self.__class__.__name__))


class MemoryDict(Memory):
    """Ephemeral in-memory storage."""

    def __init__(self):
        self.values = {}

    async def _save(self, key, value):
        self.values[key] = value

    async def _get(self, key, default):
        return self.values.get(key, default)


class MemoryRedis(Memory):
    """Redis storage."""

    def __init__(self):
        host = os.getenv('REDIS_HOST', 'localhost')
        port = os.getenv('REDIS_PORT', 6379)
        db = os.getenv('REDIS_DB', 0)
        self.r = redis.StrictRedis(host, port, db)
        # Test connection. Raises redis.exceptions.ConnectionError.
        self.r.ping()

    async def _save(self, key, value):
        json_data = json.dumps(value)
        self.r.set(key, json_data)

    async def _get(self, key, default=None):
        raw_data = self.r.get(key) or default
        try:
            json_data = json.loads(raw_data)
        except Exception as e:
            log.critical('Could not load json data! %s' % e)
            return raw_data

        return json_data
