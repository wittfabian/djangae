default_app_config = 'djangae.contrib.search.apps.SearchConfig'

from .document import (  # noqa
    AtomField,
    DateTimeField,
    Document,
    NumberField,
    TextField,
)

from .index import Index
