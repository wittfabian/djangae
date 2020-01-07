import os
from setuptools import setup, find_packages


NAME = 'djangae'
PACKAGES = find_packages()
DESCRIPTION = 'Django integration with Google App Engine'
URL = "https://github.com/potatolondon/djangae"
LONG_DESCRIPTION = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
AUTHOR = 'Potato London Ltd.'

EXTRAS = {
    "test": ["bs4"],
}

setup(
    name=NAME,
    version='2.0.0',
    packages=PACKAGES,

    # metadata for upload to PyPI
    author=AUTHOR,
    author_email='mail@p.ota.to',
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    keywords=["django", "Google App Engine", "GAE"],
    url=URL,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Framework :: Django :: 2.0',
        'Framework :: Django :: 2.1',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],

    include_package_data=True,
    # dependencies
    install_requires=[
        'django-gcloud-connectors @ https://github.com/potatolondon/django-gcloud-connectors/archive/master.zip#egg=django-gcloud-connectors'
    ],
    extras_require=EXTRAS,
    tests_require=EXTRAS['test'],
)
