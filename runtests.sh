#!/bin/bash

virtualenv venv
. venv/bin/activate

cd testapp; python install_deps.py
./runtests.sh

deactivate
rm -r django_tests
cd ..; rm -rf venv
