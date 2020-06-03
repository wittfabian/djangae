from django.apps import apps
from django.conf import settings

CUSTOM_PERMISSIONS = getattr(settings, "GOOGLEAUTH_CUSTOM_PERMISSIONS", {})


def get_permission_choices():
    """
        Returns a list of permissions that can be set
        for users. Defaults are the same as Django
        (https://docs.djangoproject.com/en/3.0/topics/auth/default/#default-permissions)
    """

    DEFAULT_PERMISSIONS = ("add", "change", "delete", "view")
    GLOBAL_PERMISSIONS = tuple(
        list(DEFAULT_PERMISSIONS) + list(CUSTOM_PERMISSIONS.get('__all__', []))
    )

    result = []

    for app in apps.get_app_configs():
        for model in app.get_models():
            model_name = str(type(model))
            app_model = "%s.%s" % (model._meta.app_label, model_name)

            codenames = list(GLOBAL_PERMISSIONS) + list(CUSTOM_PERMISSIONS.get(app_model, []))

            for permission in codenames:
                result.append(
                    "%s.%s_%s" % (
                        model._meta.app_label,
                        permission,
                        model_name.lower()
                    )
                )

    return result
