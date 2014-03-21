import logging
import os
import sys

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

def find_project_root():
    """
        Go through the path, and look for manage.py
    """
    for path in sys.path:
        abs_path = os.path.join(os.path.abspath(path), "manage.py")
        if os.path.exists(abs_path):
            return os.path.dirname(abs_path)

    raise RuntimeError("Unable to locate manage.py on sys.path")

def data_root():
    path = os.path.join(find_project_root(), ".gaedata")
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def application_id():
    setup_paths()
    from google.appengine.api import app_identity

    try:
        result = app_identity.get_application_id()
    except AttributeError:
        result = None

    if not result:
        from google.appengine.tools import dev_appserver
        appconfig = dev_appserver.LoadAppConfig(
            find_project_root(), {},
            default_partition='dev'
        )[0]

        os.environ['APPLICATION_ID'] = appconfig.application
        result = app_identity.get_application_id()


    return result

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

def appengine_on_path():
    try:
        from google.appengine.api import apiproxy_stub_map
        apiproxy_stub_map #Silence pylint
        return True
    except ImportError:
        return False

def setup_built_in_library_paths():
    from dev_appserver import fix_sys_path
    fix_sys_path()

    django_version = 1.5 #FIXME: Read this from app.yaml, and throw if not supported

    if django_version != 1.4:
        #Remove default django
        sys.path = [ x for x in sys.path if "django-1.4" not in x ]

    django_folder = "django-" + str(django_version)
    sys.path.insert(1, os.path.join(os.environ['APP_ENGINE_SDK'], "lib", django_folder))


def datastore_available():
    from google.appengine.api import apiproxy_stub_map
    return bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))

def on_production():
    return 'SERVER_SOFTWARE' in os.environ and not os.environ['SERVER_SOFTWARE'].startswith("Development")

def in_testing():
    return "test" in sys.argv

def setup_paths():
    if not appengine_on_path():
        for k in [k for k in sys.modules if k.startswith('google')]:
            del sys.modules[k]

        for path in possible_sdk_locations():
            if os.path.exists(path):
                os.environ['APP_ENGINE_SDK'] = path
                sys.path.insert(1, path)
                logging.info("Using App Engine SDK at '%s'", path)
                break
        else:
            logging.error("Unable to locate the App Engine SDK")
            sys.exit(1)

        #Configure App Engine's built in libraries
        setup_built_in_library_paths()
