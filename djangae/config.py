

from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from djangae.environment import application_id

from .models import AppConfigBase  # noqa, this just makes a nicer import for users


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
