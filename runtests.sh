#!/bin/bash

virtualenv venv
. venv/bin/activate

cd testapp; python install_deps.py
./runtests.sh

deactivate
cd ..; rm -rf venv
