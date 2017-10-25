#!/usr/bin/env python
import argparse
import os
import pprint
import stat
import shutil
import subprocess
import sys
import tarfile

from StringIO import StringIO
from zipfile import ZipFile
from urllib import urlopen


PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, "requirements.txt")
SITE_PACKAGES_DIR = os.path.join(PROJECT_DIR, "libs")
AVAILABLE_APPENGINE_SDKS_DIR = SITE_PACKAGES_DIR

APPENGINE_TARGET_DIR = os.path.join(SITE_PACKAGES_DIR, "google_appengine")

DJANGO_VERSION = os.environ.get("DJANGO_VERSION", "1.8")
APPENGINE_SDK_VERSION = os.environ.get("SDK_VERSION", "1.9.54")

INSTALL_APPENGINE_SDK = "--install_sdk" in sys.argv

# Google move versions from 'featured' to 'deprecated' when they bring
# out new releases


DJANGO_VERSION = os.environ.get("DJANGO_VERSION", "1.8")


if any([x in DJANGO_VERSION for x in ['master', 'a', 'b', 'rc']]):
    # For master, beta, alpha or rc versions, get exact versions
    DJANGO_FOR_PIP = "https://github.com/django/django/archive/{}.tar.gz".format(DJANGO_VERSION)
else:
    # For normal (eg. 1.8, 1.9) releases, get latest (.x)
    DJANGO_FOR_PIP = "https://github.com/django/django/archive/stable/{}.x.tar.gz".format(DJANGO_VERSION)


def install_appengine_sdk(target_version):
    FEATURED_SDK_REPO = "https://storage.googleapis.com/appengine-sdks/featured/"
    DEPRECATED_SDK_REPO = "https://storage.googleapis.com/appengine-sdks/deprecated/%s/" % target_version.replace('.', '')

    if not os.path.exists(SITE_PACKAGES_DIR):
        os.makedirs(SITE_PACKAGES_DIR)

    installed_version, available_versions = locally_available_sdk_versions()
    if installed_version == target_version:
        print('Appengine SDK {} is already the default version'.format(installed_version))
        return

    elif target_version in available_versions:
        available_version_sub_dir = available_versions[target_version]
        symlink_sdk_version(
            os.path.join(AVAILABLE_APPENGINE_SDKS_DIR, available_version_sub_dir, 'google_appengine')
        )
        print('Switched Appengine SDK {} -> {}'.format(installed_version, target_version))
        return

    # Download the SDK zip file
    print('Downloading and unpacking Appengine SDK {}...'.format(target_version))
    APPENGINE_SDK_FILENAME = "google_appengine_{}.zip".format(target_version)
    sdk_file = urlopen(FEATURED_SDK_REPO + APPENGINE_SDK_FILENAME)
    if sdk_file.getcode() == 404:
        sdk_file = urlopen(DEPRECATED_SDK_REPO + APPENGINE_SDK_FILENAME)
    elif sdk_file.getcode() >= 299:
        raise Exception(
            'App Engine SDK could not be found. {} returned code {}.'.format(sdk_file.geturl(), sdk_file.getcode())
        )

    # extract the SDK and save it
    zipfile = ZipFile(StringIO(sdk_file.read()))
    appengine_sdk_path = os.path.join(SITE_PACKAGES_DIR, 'google_appengine_{}'.format(target_version))
    zipfile.extractall(appengine_sdk_path)

    # Make sure the dev_appserver and appcfg are executable
    for module in ("dev_appserver.py", "appcfg.py"):
        app = os.path.join(appengine_sdk_path, 'google_appengine', module)
        st = os.stat(app)
        os.chmod(app, st.st_mode | stat.S_IEXEC)

    # symlink the target version to be the default
    symlink_sdk_version(
        os.path.join(appengine_sdk_path, 'google_appengine')
    )
    print('Appengine SDK {} is now installed'.format(target_version))


def symlink_sdk_version(target_version_path):
    appengine_sdk_symlink_path = os.path.join(SITE_PACKAGES_DIR, 'google_appengine')
    if os.path.islink(appengine_sdk_symlink_path):
        os.unlink(appengine_sdk_symlink_path)
    elif os.path.exists(appengine_sdk_symlink_path):
        shutil.rmtree(appengine_sdk_symlink_path)

    os.symlink(target_version_path, appengine_sdk_symlink_path)


def locally_available_sdk_versions():
    try:
        installed_version = None
        with open(os.path.join(APPENGINE_TARGET_DIR, 'VERSION')) as f:
            line = f.readline()
            installed_version = line.split('"')[1]
    except IOError:
        pass

    # {version: path, ...}
    available_versions = {
        path.split('_')[2]: path
        for path in get_immediate_subdirectories(AVAILABLE_APPENGINE_SDKS_DIR)
        if path.startswith('google_appengine_')
    }

    return installed_version, available_versions


def get_immediate_subdirectories(path):
    return [
        name
        for name in os.listdir(path)
        if os.path.isdir(os.path.join(path, name))
    ]


def install_python_dependencies():
    print("Running pip...")
    args = ["pip", "install", "--no-deps", "-r", REQUIREMENTS_FILE, "-t", SITE_PACKAGES_DIR, "-I"]
    p = subprocess.Popen(args)
    p.wait()

    print("Installing Django {}".format(DJANGO_VERSION))
    args = ["pip", "install", "--no-deps", DJANGO_FOR_PIP, "-t", SITE_PACKAGES_DIR, "-I", "--no-use-wheel"]
    p = subprocess.Popen(args)
    p.wait()

    print("Installing Django tests from {}".format(DJANGO_VERSION))
    django_tgz = urlopen(DJANGO_FOR_PIP)

    tar_file = tarfile.open(fileobj=StringIO(django_tgz.read()))
    for filename in tar_file.getnames():
        if filename.startswith("django-stable-{}.x/tests/".format(DJANGO_VERSION)) or \
                filename.startswith("django-master/tests/") or \
                filename.startswith("django-{}/tests/".format(DJANGO_VERSION)):
            tar_file.extract(filename, os.path.join(SITE_PACKAGES_DIR))


if __name__ == '__main__':
    argv = sys.argv[:]
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk-version', default=APPENGINE_SDK_VERSION)
    parser.add_argument('--list-cached-sdk-versions', action='store_true')
    parsed_args = parser.parse_args(argv[1:])

    if parsed_args.list_cached_sdk_versions:
        installed_version, available_versions = locally_available_sdk_versions()
        print(
            'Installed SDK version: {}\n'
            'Cached versions: {}'
            .format(installed_version, ', '.join(available_versions.keys()))
        )
        sys.exit()

    install_appengine_sdk(target_version=parsed_args.sdk_version)
    install_python_dependencies()
