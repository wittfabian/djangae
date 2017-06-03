"""
WSGI config for testapp project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/
"""

from google.appengine.ext import vendor
vendor.add('libs')

import os  # noqa
from django.core.wsgi import get_wsgi_application  # noqa
from djangae.wsgi import DjangaeApplication  # noqa

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'testapp.settings')
application = DjangaeApplication(get_wsgi_application())
