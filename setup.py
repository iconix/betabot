import os
from setuptools import setup, find_packages

DIR = os.path.dirname(os.path.realpath(__file__))

setup(
    name = "betabot",
    version = "0.1.0",
    author = "Nadja Rhodes",
    author_email = "narhodes1+blog@gmail.com",
    description = ("Bot that connects to Slack."),
    license = "Apache License, Version 2.0",
    keywords = "slack, chat, irc, hubot, alphabot",
    url = "https://github.com/iconix/betabot",
    packages=find_packages(),  # TODO: PEP420PackageFinder.find ?
    python_requires='>=3.8',
    long_description=open('%s/README.md' % DIR).read(),
    install_requires=open('%s/requirements.txt' % DIR).readlines(),
    entry_points={
        'console_scripts': [
            'betabot = betabot.app:start_ioloop'
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Topic :: Software Development',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Operating System :: POSIX',
        'Natural Language :: English',
    ],
)
