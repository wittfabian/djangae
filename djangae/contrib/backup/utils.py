from django.conf import settings

SETTINGS_PREFIX = "DJANGAE_BACKUP_"


def get_datastore_setting(name, required=True, default=None):
    settings_name = "{}{}".format(SETTINGS_PREFIX, name)
    if required and not hasattr(settings, settings_name):
        raise Exception("{} is required".format(settings_name))

    return getattr(settings, settings_name, default)

