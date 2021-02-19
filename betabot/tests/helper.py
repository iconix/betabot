import mock
from tornado import gen

__author__ = 'Nadja Rhodes <narhodes1+blog@gmail.com>'


def mock_tornado(*args, **kwargs):
    m = mock.Mock(*args, **kwargs)
    if not len(args) and not kwargs.get('return_value'):
        m.return_value = gen.maybe_future(mock_tornado)
    return m
