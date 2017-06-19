"""
Django settings for testprodapp project.

For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""
import os
import random
import django
import djangae.environment
from djangae.settings_base import *  # noqa

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


DATABASES = {
    "default": {
        'ENGINE': 'djangae.db.backends.spanner',
        'INSTANCE': 'spanner-test',
        'DATABASE': 'spanner-test',
        'PROJECT': 'djangae-cloud',
        'CREDENTIALS_JSON': ".cloud-spanner-credentials"
    }
}


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/dev/howto/deployment/checklist/

if djangae.environment.is_production_environment():
    DEBUG = False
    SECRET_KEY = ''.join([
        random.SystemRandom().choice('abcdefghijklmnopqrstuvwxyz0123456789')
        for i in range(50)
        ])
    ALLOWED_HOSTS = ['.appspot.com']
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
else:
    DEBUG = True
    SECRET_KEY = '&x$ts1u)tx#5zsi84555$(@mydbz06&q23p8=c6fs1!d4%1a^u'

# Application definition

INSTALLED_APPS = (
    'djangae',
    'django.contrib.admin',
    'djangae.contrib.gauth_sql',
    'django.contrib.auth',
    'djangae.contrib.security',
    'django.contrib.contenttypes',
    'djangae.contrib.contenttypes',
    'django.contrib.sessions',
    'testapp',
)

MIDDLEWARE = (
    'djangae.contrib.security.middleware.AppEngineSecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'djangae.contrib.gauth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'session_csrf.CsrfMiddleware',
)

if tuple(django.VERSION[:2]) < (1, 10):
    MIDDLEWARE_CLASSES = MIDDLEWARE


ROOT_URLCONF = 'testapp.urls'
SITE_ID = 1
WSGI_APPLICATION = 'wsgi.application'


# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/dev/howto/static-files/

STATIC_ROOT = BASE_DIR + 'static'
STATIC_URL = '/static/'

# Here because of "You haven't defined a TEMPLATES setting" deprecation message
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': [
            'templates',
        ],
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth'
            ],
            'debug': DEBUG,
        },
    },
]

AUTHENTICATION_BACKENDS = (
    'djangae.contrib.gauth_sql.backends.AppEngineUserAPIBackend',
)

AUTH_USER_MODEL = 'gauth_sql.GaeUser'
LOGIN_URL = 'djangae_login_redirect'

