#!/usr/bin/env python2
import json
import os
import subprocess
import sys
import tarfile
from StringIO import StringIO
from urllib import urlopen

PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, "requirements.txt")
TARGET_DIR = os.path.join(PROJECT_DIR, "libs")

DJANGO_VERSION = os.environ.get("DJANGO_VERSION", "1.11")
INSTALL_APPENGINE_SDK = "--install-sdk" in sys.argv

if any([x in DJANGO_VERSION for x in ['master', 'a', 'b', 'rc']]):
    # For master, beta, alpha or rc versions, get exact versions
    DJANGO_FOR_PIP = "https://github.com/django/django/archive/{}.tar.gz".format(DJANGO_VERSION)
else:
    # For normal (eg. 1.8, 1.9) releases, get latest (.x)
    DJANGO_FOR_PIP = "https://github.com/django/django/archive/stable/{}.x.tar.gz".format(DJANGO_VERSION)


def app_engine_is_installed():
    data = subprocess.check_output([
        "gcloud", "components", "list", "--filter=app-engine-python", "--format=json"
    ])

    data = json.loads(data)
    # Results are alphabetical so the first result should always be the
    # normal app-engine-python and not app-engine-python-extras
    data = sorted(data, key=lambda x: x["id"])
    assert(data[0]["id"] == "app-engine-python")
    return data[0]["state"]["name"] != "Not Installed"


def install_app_engine():
    subprocess.check_call(
        ["gcloud", "components", "install", "app-engine-python"]
    )


if __name__ == '__main__':
    if INSTALL_APPENGINE_SDK or not app_engine_is_installed():
        print('Downloading the AppEngine SDK...')
        install_app_engine()
    else:
        print('Not updating SDK as it exists. Pass --install-sdk to install it.')

    print("Running pip...")
    args = ["pip2", "install", "-r", REQUIREMENTS_FILE, "-t", TARGET_DIR, "-I", "--upgrade"]
    p = subprocess.Popen(args)
    p.wait()

    print("Installing Django {}".format(DJANGO_VERSION))
    args = ["pip2", "install", "--no-deps", DJANGO_FOR_PIP, "-t", TARGET_DIR, "-I", "--no-binary", ":all:", "--upgrade"]
    p = subprocess.Popen(args)
    p.wait()

    print("Installing Django tests from {}".format(DJANGO_VERSION))
    django_tgz = urlopen(DJANGO_FOR_PIP)

    tar_file = tarfile.open(fileobj=StringIO(django_tgz.read()))
    for filename in tar_file.getnames():
        if filename.startswith("django-stable-{}.x/tests/".format(DJANGO_VERSION)) or \
                filename.startswith("django-master/tests/") or \
                filename.startswith("django-{}/tests/".format(DJANGO_VERSION)):
            tar_file.extract(filename, os.path.join(TARGET_DIR))
