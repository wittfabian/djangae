from django.db import DEFAULT_DB_ALIAS, router
from django.db.models import get_model, get_models, signals, UnavailableApp
from django.contrib.auth import (models as auth_app, get_permission_codename,
    get_user_model)
from django.contrib.auth.management import _get_all_permissions

def create_permissions(app, created_models, verbosity, db=DEFAULT_DB_ALIAS, **kwargs):
    try:
        get_model('auth', 'Permission')
    except UnavailableApp:
        return

    if not router.allow_syncdb(db, auth_app.Permission):
        return

    from django.contrib.contenttypes.models import ContentType

    app_models = get_models(app)

    # This will hold the permissions we're looking for as
    # (content_type, (codename, name))
    searched_perms = list()
    # The codenames and ctypes that should exist.
    ctypes = set()
    for klass in app_models:
        # Force looking up the content types in the current database
        # before creating foreign keys to them.
        ctype = ContentType.objects.db_manager(db).get_for_model(klass)
        ctypes.add(ctype)
        for perm in _get_all_permissions(klass._meta, ctype):
            searched_perms.append((ctype, perm))

    # Find all the Permissions that have a content_type for a model we're
    # looking for.  We don't need to check for codenames since we already have
    # a list of the ones we're going to create.
    ctypes_to_get = list(ctypes)

    all_perms = []
    while ctypes_to_get:
        all_perms.extend(list(auth_app.Permission.objects.using(db).filter(
            content_type__in=ctypes_to_get[:30],
        ).values_list(
            "content_type", "codename"
        )))
        ctypes_to_get = ctypes_to_get[30:]

    ctypes_to_get = set(ctypes_to_get)

    perms = [
        auth_app.Permission(codename=codename, name=name, content_type=ctype)
        for ctype, (codename, name) in searched_perms
        if (ctype.pk, codename) not in all_perms
    ]
    auth_app.Permission.objects.using(db).bulk_create(perms)
    if verbosity >= 2:
        for perm in perms:
            print("Adding permission '%s'" % perm)

#Disconnect the default create_permissions handler which tries to do too many IN queries in some cases
signals.post_syncdb.disconnect(dispatch_uid="django.contrib.auth.management.create_permissions")

#Connect our one in its place
signals.post_syncdb.connect(create_permissions,
    dispatch_uid="djangae.contrib.auth.management.create_permissions")