
DEFAULT_FILE_STORAGE = 'djangae.storage.BlobstoreStorage'
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_HANDLERS = (
    'djangae.storage.BlobstoreFileUploadHandler',
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
)

DATABASES = {
    'default': {
        'ENGINE': 'djangae.db.backends.appengine'
    }
}

GENERATE_SPECIAL_INDEXES_DURING_TESTING = False
