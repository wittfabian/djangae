import logging
import os
import sys

def find_project_root():
    """
        Go through the path, and look for manage.py
    """
    for path in sys.path:
        abs_path = os.path.join(os.path.abspath(path), "manage.py")
        if os.path.exists(abs_path):
            return os.path.dirname(abs_path)

    raise RuntimeError("Unable to locate manage.py on sys.path")

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

def datastore_available():
    from google.appengine.api import apiproxy_stub_map
    return bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))

def on_production():
    return 'SERVER_SOFTWARE' in os.environ and not os.environ['SERVER_SOFTWARE'].startswith("Development")

def setup_paths():
    if not appengine_on_path():
        for path in possible_sdk_locations():
            if os.path.exists(path):
                sys.path.insert(1, path)
                logging.info("Using App Engine SDK at '%s'", path)
                break
        else:
            logging.error("Unable to locate the App Engine SDK")
            sys.exit(1)

        #Configure App Engine's built in libraries
        setup_built_in_library_paths()
