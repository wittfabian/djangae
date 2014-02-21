#!/usr/bin/env python
# -*- coding: utf-8 -*-

from django.db import models

EMPTY_ITER = ()

class AbstractIterableField(models.Field):
    """
    Abstract field for fields for storing iterable data type like
    ``list``, ``set`` and ``dict``.

    You can pass an instance of a field as the first argument.
    If you do, the iterable items will be piped through the passed
    field's validation and conversion routines, converting the items
    to the appropriate data type.
    """

    def __init__(self, item_field=None, *args, **kwargs):
        default = kwargs.get(
            'default', None if kwargs.get('null') else EMPTY_ITER)

        # Ensure a new object is created every time the default is
        # accessed.
        if default is not None and not callable(default):
            kwargs['default'] = lambda: self._type(default)

        super(AbstractIterableField, self).__init__(*args, **kwargs)

        # Either use the provided item_field or a RawField.
        if item_field is None:
            item_field = RawField()
        elif callable(item_field):
            item_field = item_field()
        self.item_field = item_field

        # We'll be pretending that item_field is a field of a model
        # with just one "value" field.
        assert not hasattr(self.item_field, 'attname')
        self.item_field.set_attributes_from_name('value')

    def contribute_to_class(self, cls, name):
        self.item_field.model = cls
        self.item_field.name = name
        super(AbstractIterableField, self).contribute_to_class(cls, name)

        # If items' field uses SubfieldBase we also need to.
        item_metaclass = getattr(self.item_field, '__metaclass__', None)
        if issubclass(item_metaclass, models.SubfieldBase):
            setattr(cls, self.name, Creator(self))

    def _map(self, function, iterable, *args, **kwargs):
        """
        Applies the function to items of the iterable and returns
        an iterable of the proper type for the field.

        Overriden by DictField to only apply the function to values.
        """
        return self._type(function(element, *args, **kwargs)
                          for element in iterable)

    def to_python(self, value):
        """
        Passes value items through item_field's to_python.
        """
        if value is None:
            return None
        return self._map(self.item_field.to_python, value)

    def pre_save(self, model_instance, add):
        """
        Gets our value from the model_instance and passes its items
        through item_field's pre_save (using a fake model instance).
        """
        value = getattr(model_instance, self.attname)
        if value is None:
            return None
        return self._map(
            lambda item: self.item_field.pre_save(
                _FakeModel(self.item_field, item), add),
            value)

    def get_db_prep_save(self, value, connection):
        """
        Applies get_db_prep_save of item_field on value items.
        """
        if value is None:
            return None
        return self._map(self.item_field.get_db_prep_save, value,
                         connection=connection)

    def get_db_prep_lookup(self, lookup_type, value, connection,
                           prepared=False):
        """
        Passes the value through get_db_prep_lookup of item_field.
        """

        # TODO/XXX: Remove as_lookup_value() once we have a cleaner
        # solution for dot-notation queries.
        # See: https://groups.google.com/group/django-non-relational/browse_thread/thread/6056f8384c9caf04/89eeb9fb22ad16f3).
        if hasattr(value, 'as_lookup_value'):
            value = value.as_lookup_value(self, lookup_type, connection)

        return self.item_field.get_db_prep_lookup(
            lookup_type, value, connection=connection, prepared=prepared)

    def validate(self, values, model_instance):
        try:
            iter(values)
        except TypeError:
            raise ValidationError("Value of type %r is not iterable." %
                                  type(values))

    def formfield(self, **kwargs):
        raise NotImplementedError("No form field implemented for %r." %
                                  type(self))


class ListField(AbstractIterableField):
    """
    Field representing a Python ``list``.

    If the optional keyword argument `ordering` is given, it must be a
    callable that is passed to :meth:`list.sort` as `key` argument. If
    `ordering` is given, the items in the list will be sorted before
    sending them to the database.
    """
    _type = list

    def __init__(self, *args, **kwargs):
        self.ordering = kwargs.pop('ordering', None)
        if self.ordering is not None and not callable(self.ordering):
            raise TypeError("'ordering' has to be a callable or None, "
                            "not of type %r." % type(self.ordering))
        super(ListField, self).__init__(*args, **kwargs)

    def get_internal_type(self):
        return 'ListField'

    def pre_save(self, model_instance, add):
        value = getattr(model_instance, self.attname)
        if value is None:
            return None
        if value and self.ordering:
            value.sort(key=self.ordering)
        return super(ListField, self).pre_save(model_instance, add)


class SetField(AbstractIterableField):
    """
    Field representing a Python ``set``.
    """
    _type = set

    def get_internal_type(self):
        return 'SetField'

    def value_to_string(self, obj):
        """
        Custom method for serialization, as JSON doesn't support
        serializing sets.
        """
        return list(self._get_val_from_obj(obj))

