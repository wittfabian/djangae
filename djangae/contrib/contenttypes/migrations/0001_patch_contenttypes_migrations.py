# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.migrations.operations.base import Operation
from djangae.contrib.contenttypes.models import SimulatedContentTypeManager


class PatchMigrationsOperation(Operation):

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def state_forwards(self, app_label, state):
        """ Patch manager on ModelState during migrations """
        contenttype = state.models[('contenttypes', 'contenttype')]
        contenttype.managers[0] = ('objects', SimulatedContentTypeManager(model=contenttype))


def get_installed_app_labels():
    """ Get the app labels, because settings.INSTALLED_APPS doesn't necessarily give us the labels. 
        Remove django.contrib.contenttypes because we want it to run before us. 
        Return list of tuples like ('admin', '__first__') 
    """
    from django.apps import apps
    app_labels = [app.label for app in apps.get_app_configs() if app.label != 'contenttypes']
    return [(x, '__first__') for x in app_labels]
    

class Migration(migrations.Migration):

    run_before = get_installed_app_labels()
    
    dependencies = [
        ('contenttypes', '__first__')
    ]

    operations = [
        PatchMigrationsOperation(),
    ]
