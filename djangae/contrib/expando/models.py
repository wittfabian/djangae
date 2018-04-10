from django.db import models
from django.utils import six


class ExpandoFieldOverwrittenError(Exception):
    pass


class ExpandoModel(models.Model):
    PROTECT_AGAINST_OVERWRITE = True

    def __init__(self, *args, **kwargs):
        self._expando_registry = {}

        # Remove expando values from the kwargs, otherwise
        # Django complains about them not being valid fields
        kwargs, expandos = {}, {}
        for k, v in kwargs.items():
            if isinstance(v, E):
                expandos[k] = v
            else:
                kwargs[k] = v

        super(ExpandoModel, self).__init__(*args, **kwargs)

        # Set the expando values
        for k, v in expandos.items():
            setattr(self, k, v)

    class Meta:
        abstract = True

    def _add_expando_field(self, attr, value):
        self._expando_registry[attr] = value.field_class()

    def _remove_expando_field(self, attr):
        self._expando_registry.pop(attr, None)

    def __delattr__(self, attr):
        if attr in self._expando_registry:
            self._remove_expando_field(attr)
        super(ExpandoModel, self).__delattr__(attr)

    def __setattr__(self, attr, value):
        if isinstance(value, E):
            self._add_expando_field(attr, value)
        elif attr in getattr(self, "_expando_registry", {}):
            # If you assign anything but an E object, the expando field will be replaced
            # with a normal attribute. By default we protect against this, but you can disable it
            # in your subclass.
            if self.PROTECT_AGAINST_OVERWRITE:
                raise ExpandoFieldOverwrittenError(
                    "Tried to overwrite an expando field with an attribute. Did you mean {} = E({})?".format(
                        attr, value
                    )
                )
            self._remove_expando_field(attr)

        return super(ExpandoModel, self).__setattr__(attr, value)


class NullField(models.IntegerField):
    def __init__(self, *args, **kwargs):
        kwargs["null"] = True
        super(NullField, self).__init__(*args, **kwargs)


class E(object):
    def __init__(self, value):
        self._value = value

        self.field_class  # Sanity check that we can actually get a field for this type

    @property
    def field_class(self):
        if isinstance(self._value, six.integer_types):
            return models.IntegerField
        elif isinstance(self._value, six.string_types):
            return models.CharField
        elif isinstance(self._value, bool):
            return models.BooleanField
        elif self._value is None:
            return NullField
        else:
            raise TypeError("Unsupported type for Expando field")
