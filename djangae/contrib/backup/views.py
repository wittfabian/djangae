import logging
from google.appengine.api import taskqueue

from django.apps import apps
from django.conf import settings
from django.http import HttpResponse
from djangae.environment import application_id

from .utils import get_backup_setting

logger = logging.getLogger(__name__)

GAE_BUILTIN_MODULE = "ah-builtin-python-bundle"
BACKUP_HANDLER = "/_ah/datastore_admin/backup.create"


def create_datastore_backup(request):
    """Creates a datastore backup based on the DS_BACKUP_X settings
    """
    base_url = "http://{module}-dot-{app_id}.appspot.com{backup_handler}".format(
        module=GAE_BUILTIN_MODULE,
        app_id=application_id(),
        backup_handler=BACKUP_HANDLER
    )

    enabled = get_backup_setting("ENABLED")
    if not enabled:
        msg = "DS_BACKUP_ENABLED is False. Not backing up"
        logger.info(msg)
        return HttpResponse(msg)

    gcs_bucket = get_backup_setting("GCS_BUCKET")
    backup_name = get_backup_setting("NAME")
    queue = get_backup_setting("QUEUE", required=False)
    exclude_models = get_backup_setting("EXCLUDE_MODELS", required=False, default=[])
    exclude_apps = get_backup_setting("EXCLUDE_APPS", required=False, default=[])

    models = []
    for model in apps.get_models(include_auto_created=True):
        app_label = model._meta.app_label
        object_name = model._meta.object_name
        model_def = "{}.{}".format(app_label, object_name)

        if app_label in exclude_apps:
            logger.info(
                "Not backing up {} due to {} being in DS_BACKUP_EXCLUDE_APPS".format(
                    model_def, app_label))
            continue

        if model_def in exclude_models:
            logger.info(
                "Not backing up {} as it is present in DS_BACKUP_EXCLUDE_MODELS".format(
                    model_def))
            continue

        logger.info("Backing up {}".format(model_def))
        models.append(model)

    if not models:
        raise Exception("No models to back up")

    kinds = "&amp;kind=".join(m._meta.db_table for m in models)

    backup_url = (
        "{backup_handler}"
        "?name={backup_name}"
        "&amp;gs_bucket_name={gcs_bucket}"
        "&amp;filesystem=gs"
        "&amp;kind={kinds}"
    ).format(
        backup_handler=BACKUP_HANDLER,
        backup_name=backup_name,
        gcs_bucket=gcs_bucket,
        kinds=kinds
    )

    if queue:
        backup_url += "&amp;queue={}".format(queue)

    # Backups must be started via task queue or cron.
    taskqueue.add(
        method="GET",
        url=backup_url,
        target=GAE_BUILTIN_MODULE
    )

    return HttpResponse("Started backup using URL {}".format(backup_url))
