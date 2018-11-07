import datetime

from django.conf import settings
from google.appengine.api import app_identity


SETTINGS_PREFIX = "DJANGAE_BACKUP_"


def get_backup_setting(name, required=True, default=None):
    settings_name = "{}{}".format(SETTINGS_PREFIX, name)
    if required and not hasattr(settings, settings_name):
        raise Exception("{} is required".format(settings_name))

    return getattr(settings, settings_name, default)


def get_gcs_bucket():
    """Get a bucket from DJANGAE_BACKUP_GCS_BUCKET setting. Defaults to the
    default application bucket with 'djangae-backups' appended.

    Raises an exception if DJANGAE_BACKUP_GCS_BUCKET is missing and there is
    no default bucket.
    """
    try:
        bucket = settings.DJANGAE_BACKUP_GCS_BUCKET
    except AttributeError:
        bucket = app_identity.get_default_gcs_bucket_name()

        if bucket:
            bucket = '{}/djangae-backups'.format(bucket)

    if not bucket:
        raise Exception('No DJANGAE_BACKUP_GCS_BUCKET or default bucket')

    return bucket


def get_backup_path():
    bucket = get_gcs_bucket()

    # And then we create a new, time-stamped directory for every backup run.
    # This will give us UTC even if USE_TZ=False and we aren't running on
    # App Engine (local development?).
    dt = datetime.datetime.utcnow()
    bucket_path = '{}/{:%Y%m%d-%H%M%S}'.format(bucket, dt)

    return bucket_path
