
from .views import serve_or_process

urlpatterns = [
    ("(.+)", serve_or_process)  # FIXME: Actual pattern
]
