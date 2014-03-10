import mimetypes
import os
import urlparse

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.core.files.uploadedfile import UploadedFile
from django.core.files.uploadhandler import FileUploadHandler, \
    StopFutureHandlers
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http.multipartparser import ChunkIter, Parser, LazyStream, FILE
from django.utils.encoding import smart_str, force_unicode, filepath_to_uri

from google.appengine.api import files
from google.appengine.api.images import get_serving_url, NotImageError, \
    TransformationError, BlobKeyRequiredError
from google.appengine.ext.blobstore import BlobInfo, BlobKey, delete, \
    create_upload_url, BLOB_KEY_HEADER, BLOB_RANGE_HEADER, BlobReader


def prepare_upload(request, url, **kwargs):
    return create_upload_url(url), {}


def serve_file(request, file, save_as, content_type, **kwargs):
    if hasattr(file, 'file') and hasattr(file.file, 'blobstore_info'):
        blobkey = file.file.blobstore_info.key()
    elif hasattr(file, 'blobstore_info'):
        blobkey = file.blobstore_info.key()
    else:
        raise ValueError("The provided file can't be served via the "
                         "Google App Engine Blobstore.")
    response = HttpResponse(content_type=content_type)
    response[BLOB_KEY_HEADER] = str(blobkey)
    response['Accept-Ranges'] = 'bytes'
    http_range = request.META.get('HTTP_RANGE')
    if http_range is not None:
        response[BLOB_RANGE_HEADER] = http_range
    if save_as:
        response['Content-Disposition'] = smart_str(
            u'attachment; filename=%s' % save_as)
    if file.size is not None:
        response['Content-Length'] = file.size
    return response


class BlobstoreStorage(Storage):
    """Google App Engine Blobstore storage backend."""

    def _open(self, name, mode='rb'):
        return BlobstoreFile(name, mode, self)

    def _save(self, name, content):
        name = name.replace('\\', '/')
        if hasattr(content, 'file') and \
           hasattr(content.file, 'blobstore_info'):
            data = content.file.blobstore_info
        elif hasattr(content, 'blobstore_info'):
            data = content.blobstore_info
        elif isinstance(content, File):
            guessed_type = mimetypes.guess_type(name)[0]
            file_name = files.blobstore.create(mime_type=guessed_type or 'application/octet-stream',
                                               _blobinfo_uploaded_filename=name)

            with files.open(file_name, 'a') as f:
                for chunk in content.chunks():
                    f.write(chunk)

            files.finalize(file_name)

            data = files.blobstore.get_blob_key(file_name)
        else:
            raise ValueError("The App Engine storage backend only supports "
                             "BlobstoreFile instances or File instances.")

        if isinstance(data, (BlobInfo, BlobKey)):
            # We change the file name to the BlobKey's str() value.
            if isinstance(data, BlobInfo):
                data = data.key()
            return '%s/%s' % (data, name.lstrip('/'))
        else:
            raise ValueError("The App Engine Blobstore only supports "
                             "BlobInfo values. Data can't be uploaded "
                             "directly. You have to use the file upload "
                             "handler.")

    def delete(self, name):
        delete(self._get_key(name))

    def exists(self, name):
        return self._get_blobinfo(name) is not None

    def size(self, name):
        return self._get_blobinfo(name).size

    def url(self, name):
        try:
            return get_serving_url(self._get_blobinfo(name))
        except (NotImageError, TransformationError):
            return None

    def created_time(self, name):
        return self._get_blobinfo(name).creation

    def get_valid_name(self, name):
        return force_unicode(name).strip().replace('\\', '/')

    def get_available_name(self, name):
        return name.replace('\\', '/')

    def _get_key(self, name):
        return BlobKey(name.split('/', 1)[0])

    def _get_blobinfo(self, name):
        return BlobInfo.get(self._get_key(name))

class DevBlobstoreStorage(BlobstoreStorage):
    def url(self, name):
        try:
            return super(DevBlobstoreStorage, self).url(name)
        except BlobKeyRequiredError:
            return urlparse.urljoin(settings.MEDIA_URL, filepath_to_uri(name))

class BlobstoreFile(File):

    def __init__(self, name, mode, storage):
        self.name = name
        self._storage = storage
        self._mode = mode
        self.blobstore_info = storage._get_blobinfo(name)

    @property
    def size(self):
        return self.blobstore_info.size

    def write(self, content):
        raise NotImplementedError()

    @property
    def file(self):
        if not hasattr(self, '_file'):
            self._file = BlobReader(self.blobstore_info.key())
        return self._file


class BlobstoreFileUploadHandler(FileUploadHandler):
    """
    File upload handler for the Google App Engine Blobstore.
    """
    def __init__(self, request=None):
        super(BlobstoreFileUploadHandler, self).__init__(request)
        self.content_type_extras = {}

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        """
        If a file is posted, normally `input_data` would represent the
        request object and reading from it would use `input_data._stream`
        which is a simple wrapper around `input_data.META['wsgi.input']`
        but can't be reset (i.e. seek(0)) after consuming it only once.

        It's fair to assume that we only use this uploader if there is
        NO file submitted directly to our application but to the
        blobstore.

        N.B. this *must* return None, otherwise it won't do the usual parsing
             in django.http.multiparser
        """
        # This is pretty much the same as in django.http.multiparser.MultiPartParser
        wsgi_input = self.request.META['wsgi.input']
        if hasattr(wsgi_input, 'tell'):
            original_pos = wsgi_input.tell()
        else:
            original_pos = 0
        try:
            # Instantiate the parser and stream:
            stream = LazyStream(ChunkIter(wsgi_input, self.chunk_size))

            for item_type, meta_data, field_stream in Parser(stream, boundary):
                if item_type != FILE:
                    continue

                try:
                    disposition = meta_data['content-disposition'][1]
                    field_name = disposition['name'].strip()
                except (KeyError, IndexError, AttributeError):
                    continue

                self.content_type_extras[field_name] = meta_data.get('content-type', (0, {}))[1]
        finally:
            # We need to set it back to the original position,
            # otherwise the multiparser won't be able to consume
            # this file-like object again.
            if hasattr(wsgi_input, 'seek'):
                wsgi_input.seek(original_pos)

    def new_file(self, *args, **kwargs):
        super(BlobstoreFileUploadHandler, self).new_file(*args, **kwargs)
        blobkey = self.content_type_extras[self.field_name].get('blob-key')
        self.active = blobkey is not None
        if self.active:
            self.blobkey = BlobKey(blobkey)
            raise StopFutureHandlers()

    def receive_data_chunk(self, raw_data, start):
        """
        Add the data to the StringIO file.
        """
        if not self.active:
            return raw_data

    def file_complete(self, file_size):
        """
        Return a file object if we're activated.
        """
        if not self.active:
            return

        return BlobstoreUploadedFile(
            blobinfo=BlobInfo(self.blobkey),
            charset=self.charset)


class BlobstoreUploadedFile(UploadedFile):
    """
    A file uploaded into memory (i.e. stream-to-memory).
    """

    def __init__(self, blobinfo, charset):
        super(BlobstoreUploadedFile, self).__init__(
            BlobReader(blobinfo.key()), blobinfo.filename,
            blobinfo.content_type, blobinfo.size, charset)
        self.blobstore_info = blobinfo

    def open(self, mode=None):
        pass

    def chunks(self, chunk_size=1024 * 128):
        self.file.seek(0)
        while True:
            content = self.read(chunk_size)
            if not content:
                break
            yield content

    def multiple_chunks(self, chunk_size=1024 * 128):
        return True

