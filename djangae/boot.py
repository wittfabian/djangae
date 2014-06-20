import os
import sys

from djangae.utils import application_id, data_root, find_project_root, in_testing


def find_appengine_sdk_from_path():
    import google.appengine
    return os.path.abspath(os.path.dirname(google.__path__[0]))

def setup_datastore_stubs():
    if "test" in sys.argv:
        return

    from google.appengine.datastore import datastore_sqlite_stub
    from google.appengine.api import apiproxy_stub_map
    from google.appengine.datastore import datastore_stub_util

    app_id = application_id()

    datastore = datastore_sqlite_stub.DatastoreSqliteStub(
        "dev~" + app_id,
        os.path.join(data_root(), "datastore.db"),
        require_indexes=False,
        trusted=False,
        root_path=find_project_root(),
        use_atexit=True
    )

    datastore.SetConsistencyPolicy(
          datastore_stub_util.TimeBasedHRConsistencyPolicy()
    )

    apiproxy_stub_map.apiproxy.ReplaceStub(
        'datastore_v3', datastore
    )


def configure(add_sdk_to_path=False):
    #If we are running on live, or under dev_appserver we don't need to do anything
    if "SERVER_SOFTWARE" in os.environ:
        return

    if add_sdk_to_path:
        sys.path.insert(0, locate_sdk())

    from dev_appserver import fix_sys_path
    fix_sys_path()

    from google.appengine.api import appinfo

    appengine_path = find_appengine_sdk_from_path()

    info = appinfo.LoadSingleAppInfo(open(os.path.join(find_project_root(), "app.yaml")))

    try:
        version_from_app_yaml = [ x.version for x in info.libraries if x.name == 'django' ][0]
    except IndexError:
        version_from_app_yaml = 'latest'

    latest_non_deprecated = appinfo._NAME_TO_SUPPORTED_LIBRARY['django'].non_deprecated_versions[-1]
    django_version = float(latest_non_deprecated if version_from_app_yaml == 'latest' else version_from_app_yaml)

    if django_version < 1.5:
        raise RuntimeError("Djangae only supports Django 1.5+")

    #Remove default django
    sys.path = [ x for x in sys.path if "django-1.4" not in x ]

    django_folder = "django-" + str(django_version)
    sys.path.insert(1, os.path.join(appengine_path, "lib", django_folder))

    os.environ['APP_ENGINE_SDK'] = appengine_path

    setup_datastore_stubs()



def possible_sdk_locations():
    POSSIBLE_SDK_LOCATIONS = [
        os.path.join(find_project_root(), "google_appengine"),
        os.path.join(os.path.expanduser("~"), "google_appengine"),
        os.environ.get("APP_ENGINE_SDK"),
        "/usr/local/google_appengine",
        "/Applications/GoogleAppEngineLauncher.app/Contents/Resources/GoogleAppEngine-default.bundle/Contents/Resources/google_appengine",
    ]

    for path in os.environ.get('PATH', '').split(os.pathsep):
        path = path.rstrip(os.sep)
        if path.endswith('google_appengine'):
            POSSIBLE_SDK_LOCATIONS.append(path)
    if os.name in ('nt', 'dos'):
        path = r'%(PROGRAMFILES)s\Google\google_appengine' % os.environ
        POSSIBLE_SDK_LOCATIONS.append(path)

    return [ os.path.realpath(x) for x in POSSIBLE_SDK_LOCATIONS if x ]

def locate_sdk():
    for path in possible_sdk_locations():
        if os.path.exists(path):
            return path
    else:
        raise RuntimeError("Unable to locate the App Engine SDK")
