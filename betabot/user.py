class User(object):
    """Wrapper for a User with helpful functions."""

    id = ''

    def __init__(self, payload):
        assert type(payload) == dict
        self.__dict__ = payload
        self.__dict__.update(payload['profile'])

    def __unicode__(self):
        return self.id
