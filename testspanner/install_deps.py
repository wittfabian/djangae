#!/usr/bin/env python
import os
import stat
import shutil
import subprocess
import sys

from StringIO import StringIO
from zipfile import ZipFile
from urllib import urlopen


PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, 'requirements.txt')
TARGET_DIR = os.path.join(PROJECT_DIR, 'libs')

APPENGINE_TARGET_DIR = os.path.join(TARGET_DIR, 'google_appengine')

APPENGINE_SDK_VERSION = os.environ.get('SDK_VERSION', '1.9.51')
APPENGINE_SDK_FILENAME = 'google_appengine_%s.zip' % APPENGINE_SDK_VERSION
INSTALL_APPENGINE_SDK = '--install_sdk' in sys.argv

# Google move versions from 'featured' to 'deprecated' when they bring
# out new releases
SDK_REPO_BASE = 'https://storage.googleapis.com/appengine-sdks'
FEATURED_SDK_REPO = '{0}/featured/'.format(SDK_REPO_BASE)
DEPRECATED_SDK_REPO = '{0}/deprecated/{1}/'.format(
    SDK_REPO_BASE,
    APPENGINE_SDK_VERSION.replace('.', ''),
    )


if __name__ == '__main__':

    if INSTALL_APPENGINE_SDK or not os.path.exists(APPENGINE_TARGET_DIR):

        # If we're going to install the App Engine SDK then we can just wipe
        # the entire TARGET_DIR
        if os.path.exists(TARGET_DIR):
            shutil.rmtree(TARGET_DIR)

        if not os.path.exists(os.path.join(TARGET_DIR, 'djangae')):
            p = subprocess.Popen(['git', 'checkout', '--', 'libs'])
            p.wait()

        print('Downloading the AppEngine SDK...')

        # First try and get it from the 'featured' folder
        sdk_file = urlopen(FEATURED_SDK_REPO + APPENGINE_SDK_FILENAME)
        if sdk_file.getcode() == 404:
            # Failing that, 'deprecated'
            sdk_file = urlopen(DEPRECATED_SDK_REPO + APPENGINE_SDK_FILENAME)

        # Handle other errors
        if sdk_file.getcode() >= 299:
            raise Exception(
                'App Engine SDK could not be found. {} returned code {}.'
                .format(sdk_file.geturl(), sdk_file.getcode())
                )

        zipfile = ZipFile(StringIO(sdk_file.read()))
        zipfile.extractall(TARGET_DIR)

        # Make sure the dev_appserver and appcfg are executable
        for module in ('dev_appserver.py', 'appcfg.py'):
            app = os.path.join(APPENGINE_TARGET_DIR, module)
            st = os.stat(app)
            os.chmod(app, st.st_mode | stat.S_IEXEC)
    else:
        print('Not updating SDK as it exists. Pass --install_sdk to install.')
        # In this sencario we need to wipe everything except the SDK from
        # the TARGET_DIR
        for name in os.listdir(TARGET_DIR):
            if name in ('google_appengine', 'djangae'):
                continue
            path = os.path.join(TARGET_DIR, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    print('Running pip...')
    args = [
        'pip',
        'install',
        '--no-deps',
        '-r', REQUIREMENTS_FILE,
        '-t', TARGET_DIR,
        '-I',
        ]
    p = subprocess.Popen(args)
    p.wait()
