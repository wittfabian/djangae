import copy
from collections import OrderedDict

from django.db import models
from django.utils import six


class ExpandoFieldOverwrittenError(Exception):
    pass


class ExpandoModel(models.Model):
    PROTECT_AGAINST_OVERWRITE = True

    def __init__(self, *args, **kwargs):
        self._expando_registry = OrderedDict()

        # Wrap _meta to include stuff from the expando registry
        original_meta = copy.copy(self._meta)

        def meta_factory():
            class NewMeta(original_meta.__class__):
                _instance = self

                @property
                def expando_fields(self):
                    return self._instance._expando_registry.keys()

                @property
                def concrete_fields(self):
                    return tuple([x for x in self.fields if x.concrete])

                @property
                def fields(self):
                    # Make sure that instance expando fields are returned by _meta.fields
                    fields = super(NewMeta, self).fields
                    fields = list(fields)
                    fields.extend(list(self._instance._expando_registry.values()))
                    return tuple(fields)

                def get_field(self, name):
                    if name in self._instance._expando_registry:
                        return self._instance._expando_registry[name]
                    return super(NewMeta, self).get_field(name)

            return NewMeta

        original_meta.__class__ = meta_factory()
        setattr(self, "_meta", original_meta)

        # Remove expando values from the kwargs, otherwise
        # Django complains about them not being valid fields
        new_kwargs, expandos = {}, {}
        for k, v in kwargs.items():
            if isinstance(v, E):
                expandos[k] = v
            else:
                new_kwargs[k] = v

        super(ExpandoModel, self).__init__(*args, **new_kwargs)

        # Set the expando values
        for k, v in expandos.items():
            setattr(self, k, v)

    class Meta:
        abstract = True

    def _add_expando_field(self, attr, value):
        field = value.field_class(name=attr)
        field.set_attributes_from_name(attr)
        self._expando_registry[attr] = field
        return self._expando_registry[attr]

    def _remove_expando_field(self, attr):
        self._expando_registry.pop(attr, None)

    def __delattr__(self, attr):
        if attr in self._expando_registry:
            self._remove_expando_field(attr)
        super(ExpandoModel, self).__delattr__(attr)

    def __setattr__(self, attr, value):
        if isinstance(value, E):
            field = self._add_expando_field(attr, value)
            super(ExpandoModel, self).__setattr__(field.get_attname(), value._value)
            return
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
