from functools import wraps

def additional_type_handler(func):
    @wraps(func)
    def _wrapper(self, o):
        if isinstance(o, set):
            # Treat sets as lists.
            return list(o)
        else:
            return func(self, o)

    return _wrapper

def patch():
    """
        This patches Djangos JSON encoder so it can deal with
        set(). This is necessary because otherwise we can't
        serialize SetFields
    """
    from django.core.serializers.json import DjangoJSONEncoder
    DjangoJSONEncoder.default = additional_type_handler(DjangoJSONEncoder.default)
