import os
from djangae.utils import memoized


def application_id():
    from google.appengine.api import app_identity

    try:
        result = app_identity.get_application_id()
    except AttributeError:
        result = None

    if not result:
        # Apparently we aren't running live, probably inside a management command
        from google.appengine.api import appinfo

        info = appinfo.LoadSingleAppInfo(open(os.path.join(get_application_root(), "app.yaml")))

        result = "dev~" + info.application
        os.environ['APPLICATION_ID'] = result
        result = app_identity.get_application_id()

    return result


def sdk_is_available():
    try:
        from google.appengine.api import apiproxy_stub_map
        apiproxy_stub_map  # Silence pylint
        return True
    except ImportError:
        return False


def is_production_environment():
    return not is_development_environment()


def is_development_environment():
    return 'SERVER_SOFTWARE' in os.environ and os.environ['SERVER_SOFTWARE'].startswith("Development")


def datastore_is_available():
    if not sdk_is_available():
        return False

    from google.appengine.api import apiproxy_stub_map
    return bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))


@memoized
def get_application_root():
    """Traverse the filesystem upwards and return the directory containing app.yaml"""
    path = os.path.dirname(os.path.abspath(__file__))
    app_yaml_path = os.environ.get('DJANGAE_APP_YAML_LOCATION', None)

    # If the DJANGAE_APP_YAML_LOCATION variable is setup, will try to locate
    # it from there.
    if (app_yaml_path is not None and
            os.path.exists(os.path.join(app_yaml_path, "app.yaml"))):
        return app_yaml_path

    # Failing that, iterates over the parent folders until it finds it,
    # failing when it gets to the root
    while True:
        if os.path.exists(os.path.join(path, "app.yaml")):
            return path
        else:
            parent = os.path.dirname(path)
            if parent == path:  # Filesystem root
                break
            else:
                path = parent

    raise RuntimeError("Unable to locate app.yaml. Did you add it to skip_files?")
