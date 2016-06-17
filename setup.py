import os
from setuptools import setup, find_packages


NAME = 'djangae'
PACKAGES = find_packages()
DESCRIPTION = 'Django integration with Google App Engine'
URL = "https://github.com/potatolondon/djangae"
LONG_DESCRIPTION = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
AUTHOR = 'Potato London Ltd.'

EXTRAS = {
    "test": ["webtest"],
}

setup(
    name=NAME,
    version='0.9.5',
    packages=PACKAGES,

    # metadata for upload to PyPI
    author=AUTHOR,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    keywords=["django", "Google App Engine", "GAE"],
    url=URL,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Django',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.9',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],

    include_package_data=True,
    # dependencies
    extras_require=EXTRAS,
    tests_require=EXTRAS['test'],
)
