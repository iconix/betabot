from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version('betabot')
except PackageNotFoundError:
    __version__ = '0.0.1'
