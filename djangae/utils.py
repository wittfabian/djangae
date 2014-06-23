import os
import sys


def find_project_root():
    """Traverse the filesystem upwards and return the directory containing app.yaml"""
    path = os.path.dirname(os.path.abspath(__file__))

    while True:
        if os.path.exists(os.path.join(path, "app.yaml")):
            return path
        else:
            parent = os.path.dirname(path)
            if parent == path:  # Filesystem root
                break
            else:
                path = parent

    raise RuntimeError("Unable to locate app.yaml")


def data_root():
    path = os.path.join(find_project_root(), ".gaedata")
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def application_id():
    from google.appengine.api import app_identity

    try:
        result = app_identity.get_application_id()
    except AttributeError:
        result = None

    if not result:
        #Apparently we aren't running live, probably inside a management command
        from google.appengine.api import appinfo

        info = appinfo.LoadSingleAppInfo(open(os.path.join(find_project_root(), "app.yaml")))

        result = "dev~" + info.application
        os.environ['APPLICATION_ID'] = result
        result = app_identity.get_application_id()

    return result


def appengine_on_path():
    try:
        from google.appengine.api import apiproxy_stub_map
        apiproxy_stub_map #Silence pylint
        return True
    except ImportError:
        return False


def on_production():
    return 'SERVER_SOFTWARE' in os.environ and not os.environ['SERVER_SOFTWARE'].startswith("Development")


def datastore_available():
    from google.appengine.api import apiproxy_stub_map
    return bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))


def in_testing():
    return "test" in sys.argv
