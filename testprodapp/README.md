# App for Testing Performance in a Production GCP Environment

`testprodapp` is an app that allows a user to upload a real **djangae** app to
the production Google Cloud Platform environment and test real-world scenarios
for performance or analysis.

## Preparing for upload

To upload the app, first you need to download all dependencies. You can do
this from the main `djangae` directory:

    $ ./runtests.sh --for-production-env

... or from the `testprodapp` directory:

    $ python install_deps.py

## Running unit tests

Run unit tests in the normal way:

    $ python manage.py test testapp

## Running the app locally

The app can be run locally like any other `django` project:

    $ python manage.py runserver

## Running tests

1. Start the server locally
1. Create a superuser: navigate to http://localhost:8000/auth/login_redirect
1. Navigate the admin app: http://localhost:8000/admin
1. Create some test entities: http://localhost:8000/admin/testapp/uuid/ then
   click on **Bulk Create UUIDs** to create them in batches of 100
1. Run a counting test: http://localhost:8000/admin/testapp/testresult/ then
   click on **Test Counting Entities** to run the counting test; note that the
   test defers many actions, so you may need to reload the test results page
   after a few seconds to see the results

## App architecture

For simplicity, all UI is currently in the `admin` app. Put test functionality
into a module in `testapp/prod_tests` and execute it from functions built
in `testapp/admin.py`. To add buttons look in `templates/admin/testapp` for
examples.
