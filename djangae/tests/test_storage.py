# coding: utf-8
import cStringIO
import httplib
import os
import urlparse

from google.appengine.api import urlfetch
from google.appengine.tools.devappserver2 import blob_upload, blob_image

from django.core.files.base import File, ContentFile
from django.http import HttpResponse

from djangae.test import TestCase
from djangae.storage import BlobstoreStorage

from testapp.wsgi import application


# _URL_STRING_MAP is {'GET': 1, etc} so reverse dict to convert int to string
URL_INT_TO_STRING_MAP = {v: k for k, v in urlfetch._URL_STRING_MAP.items()}

_fetch = urlfetch.fetch  # Reference to original: will be wrapped later


def urlfetch_wrapper(url, payload=None, method=urlfetch.GET, headers={},
                     validate_certificate=None, **kwargs):
    """ Wrapper for urlfetch to route blobstore URLs to test handlers. """
    # Need to include validate_certificate in args ^^ because
    # AppEngineSecurityMiddleware will introspect it.

    _, _, path, _, query, _ = urlparse.urlparse(url)

    # Only special treatment for blobstore URLs
    if path.startswith('/_ah/upload/'):
        # Blobstore upload handler is a WSGI application. `forward_app=...`
        # tells it to route the _subsequent_ POST back to Django
        app = blob_upload.Application(forward_app=application)

    elif path.startswith('/_ah/img/'):
        # Blobstore image handler is a WSGI app too
        app = blob_image.Application()

    else:
        # Not a blobstore URL – use standard urlfetch
        return _fetch(url, payload, method, headers,
                      validate_certificate=validate_certificate, **kwargs)

    environ = {
        'SERVER_NAME':    'testserver',
        'SERVER_PORT':    '80',
        'CONTENT_TYPE':   headers.get('Content-Type', None),
        'PATH_INFO':      path,
        'QUERY_STRING':   query,
        'REQUEST_METHOD': URL_INT_TO_STRING_MAP[method],
    }
    if payload:
        environ.update({
            'CONTENT_LENGTH': len(payload),
            'wsgi.input':     cStringIO.StringIO(payload),
        })
    response = HttpResponse()

    # A dummy start_response is fine because we’re just populating
    # an HttpResponse
    for s in app(environ, start_response=lambda *args: None):
        response.write(s)

    return response


class BlobstoreStorageTests(TestCase):

    # In tests urlfetch hits real URLs, so patching to correctly route to the
    # blobstore upload handler. Can’t use sleuth because it wraps the function,
    # which confuses `replace_default_argument()` in SecurityMiddleware.
    def setUp(self):
        super(BlobstoreStorageTests, self).setUp()
        urlfetch.fetch = urlfetch_wrapper

    def tearDown(self):
        urlfetch.fetch = _fetch
        super(BlobstoreStorageTests, self).tearDown()

    def test_basic_actions(self):

        storage = BlobstoreStorage()

        # Save a new file
        f = ContentFile('content', name='my_file')
        filename = storage.save('tmp', f)

        self.assertIsInstance(filename, basestring)
        self.assertTrue(filename.endswith('tmp'))

        # Check .exists(), .size() and .url()
        self.assertTrue(storage.exists(filename))
        self.assertEqual(storage.size(filename), len('content'))
        url = storage.url(filename)
        self.assertIsInstance(url, basestring)
        self.assertNotEqual(url, '')

        # Check URL can be fetched
        abs_url = urlparse.urlunparse(
            ('http', os.environ['HTTP_HOST'], url, None, None, None)
        )
        response = urlfetch.fetch(abs_url)
        self.assertEqual(response.status_code, httplib.OK)
        self.assertEqual(response.content, 'content')

        # Open it, read it
        # NOTE: Blobstore doesn’t support updating existing files.
        f = storage.open(filename)
        self.assertIsInstance(f, File)
        self.assertEqual(f.read(), 'content')

        # Delete it
        storage.delete(filename)
        self.assertFalse(storage.exists(filename))
