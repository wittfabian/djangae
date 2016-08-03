#!/bin/bash

cd testapp;

# Check for the --install_deps and --install_sdk args, and pass the other args down to manage.py test
ARGS=()
for var in "$@"; do
    if [ "$var" = '--install_deps' ]; then
        INSTALL_DEPS=true
    elif [ "$var" = '--install_sdk' ]; then
        INSTALL_DEPS=true
        INSTALL_SDK=true
    else
        ARGS[${#ARGS[@]}]="$var"
    fi
done

# If the SDK doesn't exist then we want to run install_deps anyway.  We don't need to pass
# install_sdk to it because it will detect that the SDK doesn't exist anyway.
if [ ! -d "libs/google_appengine" ]; then
    INSTALL_DEPS=true
fi

if [ -n "$INSTALL_DEPS" ]; then
    echo "Running install_deps..."
    if [ -n "$INSTALL_SDK" ]; then
        python install_deps.py --install_sdk
    else
        python install_deps.py
    fi
else
    echo "Not running install_deps.  Pass --install_deps if you want to install dependencies."
fi

python manage.py test "${ARGS[@]}"

cd ..;
