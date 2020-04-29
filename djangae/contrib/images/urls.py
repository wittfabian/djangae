
from .views import serve_or_process
from django.urls import path
from djangae.storage import _get_default_bucket_name

DEFAULT_BUCKET = _get_default_bucket_name()

urlpatterns = [
    # FIXME: Actual pattern
    path("/serve/(?P<image_path>.+)", serve_or_process, kwargs={'bucket': DEFAULT_BUCKET})
]
