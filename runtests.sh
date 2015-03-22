#!/bin/bash

virtualenv venv
. venv/bin/activate

git submodule init && git submodule update

python testapp/install_deps.py
cd testapp; ./runtests.sh

deactivate
cd ..; rm -rf venv
