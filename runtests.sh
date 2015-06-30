#!/bin/bash

cd testapp;

if [ ! -d "libs/google_appengine" ]; then
    echo "SDK directory not found, installing SDK and dependencies..."
    python install_deps.py
else
    echo "SDK directory already exists, not installing dependencies."
    echo "Run python testapp/install_deps.py manually to install/upgrade dependencies."
fi

python manage.py test "$@"
asdlfkjasdklfj

cd ..;
