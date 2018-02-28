import logging
import urllib

from django.apps import apps
from django.http import HttpResponse
from djangae.environment import task_or_admin_only
from google.appengine.api import taskqueue

from .utils import get_backup_setting, get_backup_path


logger = logging.getLogger(__name__)

GAE_BUILTIN_MODULE = "ah-builtin-python-bundle"
BACKUP_HANDLER = "/_ah/datastore_admin/backup.create"


@task_or_admin_only
def create_datastore_backup(request):
    """Creates a datastore backup based on the DJANGAE_BACKUP_X settings."""
    enabled = get_backup_setting("ENABLED")
    if not enabled:
        msg = "DJANGAE_BACKUP_ENABLED is False. Not backing up"
        logger.info(msg)
        return HttpResponse(msg)

    gcs_bucket = get_backup_path()
    backup_name = get_backup_setting("NAME", required=False, default='djangae-backups')
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
                "Not backing up {} due to {} being in DJANGAE_BACKUP_EXCLUDE_APPS".format(
                    model_def, app_label))
            continue

        if model_def in exclude_models:
            logger.info(
                "Not backing up {} as it is present in DJANGAE_BACKUP_EXCLUDE_MODELS".format(
                    model_def))
            continue

        logger.info("Backing up {}".format(model_def))
        models.append(model)

    if not models:
        raise Exception("No models to back up")

    # Build the target path and query for the task.
    params = [
        ('name', backup_name),
        ('gs_bucket_name', gcs_bucket),
        ('filesystem', 'gs'),
    ]
    params.extend(('kind', m._meta.db_table) for m in models)

    if queue:
        params.append(('queue', queue))

    query = urllib.urlencode(params, doseq=True)
    backup_url = '{}?{}'.format(BACKUP_HANDLER, query)

    # Backups must be started via task queue or cron.
    taskqueue.add(
        method="GET",
        url=backup_url,
        target=GAE_BUILTIN_MODULE
    )

    return HttpResponse("Started backup using URL {}".format(backup_url))
