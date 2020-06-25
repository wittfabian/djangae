import logging
import os
from io import (
    BytesIO,
    UnsupportedOperation,
)

import requests
from django.conf import settings
from django.core.files.storage import (
    File,
    Storage,
)
from google.cloud.exceptions import NotFound

from djangae.environment import project_id

BUCKET_KEY = "CLOUD_STORAGE_BUCKET"

logger = logging.getLogger(__name__)


def _get_storage_client():
    """Gets an instance of a google CloudStorage Client

        Note: google storage python library depends on env variables read at
        module import time, so that should be set before import if overwrite needed
    """

    is_app_engine = os.environ.get("GAE_ENV") == "standard"
    http = None

    if not is_app_engine:
        http = requests.Session()

    from google.cloud import storage
    return storage.Client(
        project=os.environ['GOOGLE_CLOUD_PROJECT'],
        _http=http,
    )


def _get_default_bucket_name():
    default_bucket = None
    p_id = project_id()
    if p_id:
        default_bucket = "{}.appspot.com".format(p_id)

    return default_bucket


def get_bucket_name():
    """Returns the configured bucket name

    Bucket name can be configured via settings[BUCKET_KEY]. If not set, it
    defaults to the GCP default bucket (<project_id>.appspot.com)

    Raises:
        ImproperlyConfigured: if neither configuration nor default can be retreived

    Returns:
        str -- name of the configured bucket
    """
    bucket_name = getattr(settings, BUCKET_KEY, None)
    if not bucket_name:
        bucket_name = _get_default_bucket_name()

    if not bucket_name:
        from django.core.exceptions import ImproperlyConfigured
        message = "{} not set or no default bucket configured".format(BUCKET_KEY)
        raise ImproperlyConfigured(message)

    return bucket_name


class CloudStorageFile(File):
    def __init__(self, bucket, name=None, mode="rb"):
        self._name = name
        self._mode = mode
        self._blob = bucket.blob(name)

    def read(self, num_bytes=None):
        if "r" not in self._mode:
            raise UnsupportedOperation("File open in '{}' mode is not readable".format(self._mode))
        if num_bytes:
            raise NotImplementedError("Specified argument 'num_bytes: {}' not supported".format(num_bytes))

        f = BytesIO()
        self._blob.download_to_file(f)
        return f.getvalue()

    def write(self, content):
        raise NotImplementedError("Write of CloudStorageFile object not currently supported.")


class CloudStorage(Storage):
    """
        Google Cloud Storage backend, set this as your default backend
        for ease of use, you can specify and non-default bucket in the
        constructor.

        You can modify objects access control by changing google_acl
        attribute to one of mentioned by docs (XML column):
        https://cloud.google.com/storage/docs/access-control/lists?hl=en#predefined-acl
    """
    def __init__(self, bucket_name=None, google_acl=None):
        self._bucket_name = bucket_name if bucket_name else get_bucket_name()
        self._client = None
        self._bucket = None
        self._google_acl = google_acl

    @property
    def client(self):
        """Returns the GCS client

        Returns:
            google.cloud.storage.Client -- GCS Client instance
        """
        if self._client is None:
            self._client = _get_storage_client()
        return self._client

    @property
    def bucket(self):
        if not self._bucket:
            try:
                self._bucket = self.client.get_bucket(self._bucket_name)
            except NotFound as e:
                logger.info("Bucket '{}' does not exist".format(self._bucket_name))
                raise e

        return self._bucket

    def get_valid_name(self, name):
        # App Engine doesn't properly deal with "./" and a blank upload_to argument
        # on a filefield results in ./filename so we must remove it if it's there.
        if name.startswith("./"):
            name = name.replace("./", "", 1)
        return name

    def exists(self, name):
        return bool(self.bucket.get_blob(name))

    def _save(self, name, content):
        # Not sure why, but it looks like django is not actually calling this
        name = self.get_valid_name(name)
        blob = self.bucket.blob(name)
        blob.upload_from_file(
            content.file, size=content.size, predefined_acl=self._google_acl
        )
        return name

    def _open(self, name, mode="r"):
        return CloudStorageFile(self._bucket, name=name, mode=mode)

    def size(self, name):
        blob = self.bucket.get_blob(name)
        if blob is None:
            raise NotFound("File {} does not exists".format(name))
        return blob.size

    def delete(self, name):
        """Delete an object by name

        Arguments:
            name {str} -- Name of the object to delete
        """
        return self._bucket.delete_blob(name)

    def url(self, name):
        return self.get_public_url(name)

    def get_public_url(self, name):
        """Gets the public URL of a blob

        Note: the public url is not guaranteed to be accessible. This depends on your bucket/object
        ACL and IAM. When using the gcs emulator, all objects are treated as publicly accessible

        Arguments:
            name {str} -- name of the blob

        Returns:
            str -- Public url
        """
        is_app_engine = os.environ.get("GAE_ENV") == "standard"
        if is_app_engine:
            blob = self.bucket.blob(name)
            return blob.public_url
        else:
            return "{}/{}/{}".format(os.environ["STORAGE_EMULATOR_HOST"], self._bucket_name, name)
