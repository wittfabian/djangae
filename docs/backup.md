# Djangae Contrib Backup

An app to help manage datastore backups.

## Basic usage

By default all registered models are backed up.

* Enable datastore admin in the Cloud Console for your application
* Add backup url to main urls.py file:
```python
    url(r'^tasks/', include('djangae.contrib.backup.urls'))
```
* Add backup entry to cron.yaml:
```yaml
cron:
- description: Scheduled datastore backups
  url: /tasks/create-datastore-backup/
  schedule: every day 07:00
```
* Add backup queue to queue.yaml:
```yaml
- name: backups
  rate: 1/s
```
* Add required settings to settings.py"
```python
DS_BACKUP_ENABLED = True
DS_BACKUP_GCS_BUCKET = "my-application-bucket"
DS_BACKUP_QUEUE = "backups"
```
* Add `'djangae.contrib.backup'` to `settings.INSTALLED_APPS` (if you want the tests to run)

## Other optional settings

### Exclude all models from certain applications:

```python
DS_BACKUP_EXCLUDE_APPS = [
    "contenttypes",
    "cspreports",
    "djangae",
    "locking",
    "osmosis",
    "sessions",
]
```

### Exclude specific models

```python
DS_BACKUP_EXCLUDE_MODELS = [
    'sessions.Session',
]
```