import os

BASE_DIR = os.path.dirname(__file__)

INSTALLED_APPS = (
    'gcloudc',
    'djangae',
    'djangae.commands',  # Takes care of emulator setup
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
