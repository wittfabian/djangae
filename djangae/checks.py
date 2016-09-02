import os

from django.core import checks
from google.appengine.tools.devappserver2.application_configuration import ModuleConfiguration

from djangae.environment import get_application_root


def check_deferred_builtin(app_configs=None, **kwargs):
    """
    Check that the deferred builtin is switched off, as it'll override Djangae's deferred handler
    """
    app_yaml_path = os.path.join(get_application_root(), "app.yaml")
    config = ModuleConfiguration(app_yaml_path)
    errors = []

    for handler in config.handlers:
        if handler.url == '/_ah/queue/deferred':
            if handler.script == 'google.appengine.ext.deferred.application':
                errors.append(
                    checks.Warning(
                        "Deferred builtin is switched on. This overrides Djangae's deferred handler",
                        hint='Remove deferred builtin from app.yaml',
                        id='djangae.W001'
                    )
                )
            break

    return errors
