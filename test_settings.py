import os

from django.urls import (
    include,
    path,
)

BASE_DIR = os.path.dirname(__file__)
STATIC_URL = "/static/"

TEST_RUNNER = "djangae.test.AppEngineDiscoverRunner"

# Set the cache during tests to local memory, which is threadsafe
# then our TestCase clears the cache in setUp()
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Default Django middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'djangae.tasks.middleware.task_environment_middleware',
]

INSTALLED_APPS = (
    'django.contrib.sessions',
    'gcloudc',
    'djangae',
    'djangae.tasks',
)

DATABASES = {
    'default': {
        'ENGINE': 'gcloudc.db.backends.datastore',
        'INDEXES_FILE': os.path.join(os.path.abspath(os.path.dirname(__file__)), "djangaeidx.yaml"),
        "PROJECT": "test",
        "NAMESPACE": "ns1",  # Use a non-default namespace to catch edge cases where we forget
    }
}

SECRET_KEY = "secret_key_for_testing"

USE_TZ = True

CSRF_USE_SESSIONS = True

CLOUD_TASKS_LOCATION = "[LOCATION]"

# Define two required task queues
CLOUD_TASKS_QUEUES = [
    {
        "name": "default"
    },
    {
        "name": "another"
    }
]

# Point the URL conf at this file
ROOT_URLCONF = __name__

urlpatterns = [
    path('tasks/', include('djangae.tasks.urls')),
    # path('images/', include('djangae.contrib.images.urls')),
]
