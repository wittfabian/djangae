import os
from setuptools import setup, find_packages


NAME = 'djangae'
PACKAGES = find_packages(exclude=["testapp", "testprodapp"])
DESCRIPTION = 'Django integration with Google App Engine'
URL = "https://github.com/potatolondon/djangae"
LONG_DESCRIPTION = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
AUTHOR = 'Potato London Ltd.'

setup(
    name=NAME,
    version='2.0.0 alpha',
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
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    # FIXME: For now, depend on master of gcloud-connectors
    install_requires=[
        'Django>=2.0,<3.0',
        'django-gcloud-connectors @ git+https://github.com/potatolondon/django-gcloud-connectors.git',
    ],
    include_package_data=True,
)
