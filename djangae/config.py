import os

import requests
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from djangae.environment import application_id
from google.cloud import (
    datastore,
    environment_vars,
)

from .models import \
    AppConfigBase  # noqa, this just makes a nicer import for users


def get_app_config_model(config_model=None):
    try:
        if not config_model:
            from django.conf import settings
            config_model = settings.DJANGAE_APP_CONFIG_MODEL

        return django_apps.get_model(config_model, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured("DJANGAE_APP_CONFIG_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "DJANGAE_APP_CONFIG_MODEL refers to model '%s' that has not been installed" %
            settings.DJANGAE_APP_CONFIG_MODEL
        )


def get_app_config(config_model=None, **defaults):
    AppConfig = get_app_config_model(config_model=config_model)
    app_id = application_id()

    assert(app_id)

    defaults.setdefault(
        "secret_key", get_random_secret_key()
    )

    return AppConfig.objects.get_or_create(
        pk=app_id, defaults=defaults
    )[0]


def get_or_create_secret_key(databases_settings_dict, app_config_model):
    params = databases_settings_dict

    # Uses the standard db_table, AppConfig can't work for secret keys
    # if you've changed this, as we can't import the model
    kind = app_config_model.lower().replace(".", "_")

    client = datastore.Client(
        namespace=params.get("NAMESPACE"),
        project=params.get("PROJECT") or os.environ["DATASTORE_PROJECT_ID"],
        # avoid a bug in the google client - it tries to authenticate even when the emulator is enabled
        # see https://github.com/googleapis/google-cloud-python/issues/5738
        _http=requests.Session if os.environ.get(environment_vars.GCD_HOST) else None,
    )

    key = client.key(kind, application_id())
    entity = client.get(key)
    if not entity:
        entity = datastore.Entity(key=key)
        entity["secret_key"] = get_random_secret_key()
        client.put(entity)

    return entity["secret_key"]
