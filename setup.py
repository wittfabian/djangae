import os
from setuptools import setup, find_packages


NAME = 'djangae'
PACKAGES = find_packages()
DESCRIPTION = 'Django integration with Google App Engine'
URL = "https://github.com/lukebpotato/djangae"
LONG_DESCRIPTION = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
AUTHOR = 'Luke Benstead'

setup(
    name=NAME,
    version='0.1',
    packages=PACKAGES,

    # metadata for upload to PyPI
    author=AUTHOR,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    keywords=["django", "Google App Engine", "GAE"],
    url=URL,
)
