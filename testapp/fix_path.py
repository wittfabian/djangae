import os
import sys


def fix_path():
    current_folder = os.path.abspath(os.path.dirname(__file__))
    lib_path = os.path.join(current_folder, "libs")

    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)

    # Djangae exists in the parent directory, but the dev_appserver sandbox won't let us access it
    # there, so it's just symlinked into the 'testapp' directory, and we don't need to add it here.

    # Adds Django and Django tests
    base_django_path = os.path.join(current_folder, "submodules", "django")
    django_path = os.path.join(base_django_path, "django")
    django_tests_path = os.path.join(base_django_path, "tests")

    if base_django_path not in sys.path:
        sys.path.insert(0, base_django_path)

    if django_path not in sys.path:
        sys.path.insert(0, django_path)

    if django_tests_path not in sys.path:
        sys.path.insert(0, django_tests_path)

    os.environ['DJANGAE_APP_YAML_LOCATION'] = current_folder
    os.environ['PYTHONPATH'] = ''

    try:
        import wrapper_util
    except ImportError:
        appengine_path = os.path.join(lib_path, "google_appengine")
        sys.path.insert(0, appengine_path)

        simplejson_path = os.path.join(appengine_path, "lib", "simplejson")
        sys.path.insert(0, simplejson_path)

    # Frustratingly, `import google` imports from the App Engine SDK, so if you install
    # any other google libraries (e.g. protobuf, gcloud) into your libs folder, they won't be found
    # unless we manually force it like this.
    if os.path.exists(os.path.join(lib_path, "google")):
        import google
        google.__path__.append(os.path.join(lib_path, "google"))
