#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.subclassing import Creator
from django.db.models.loading import get_model
from django.db.models.sql.where import Constraint
from django import forms
from django.utils.text import capfirst
from django.utils.translation import ugettext_lazy as _
from google.appengine.api.datastore import Key, AllocateIds

from djangae.db import transaction
from djangae.forms.fields import TrueOrNullFormField, IterableFieldModelChoiceFormField, ListFormField
from djangae.models import CounterShard


class _FakeModel(object):
    """
    An object of this class can pass itself off as a model instance
    when used as an arguments to Field.pre_save method (item_fields
    of iterable fields are not actually fields of any model).
    """

    def __init__(self, field, value):
        setattr(self, field.attname, value)


class RawField(models.Field):
    """
    Generic field to store anything your database backend allows you
    to. No validation or conversions are done for this field.
    """

    def get_internal_type(self):
        """
        Returns this field's kind. Nonrel fields are meant to extend
        the set of standard fields, so fields subclassing them should
        get the same internal type, rather than their own class name.
        """
        return 'RawField'

class TrueOrNullField(models.NullBooleanField):
    """A Field only storing `Null` or `True` values.

    Why? This allows unique_together constraints on fields of this type
    ensuring that only a single instance has the `True` value.

    It mimics the NullBooleanField field in it's behaviour, while it will
    raise an exception when explicitly validated, assigning something
    unexpected (like a string) and saving, will silently convert that
    value to either True or None.
    """
    __metaclass__ = models.SubfieldBase

    default_error_messages = {
        'invalid': _("'%s' value must be either True or None."),
    }
    description = _("Boolean (Either True or None)")

    def to_python(self, value):
        if value in (None, 'None', False):
            return None
        if value in (True, 't', 'True', '1'):
            return True
        msg = self.error_messages['invalid'] % str(value)
        raise ValidationError(msg)

    def get_prep_value(self, value):
        """Only ever save None's or True's in the db. """
        if value in (None, False, '', 0):
            return None
        return True

    def formfield(self, **kwargs):
        defaults = {
            'form_class': TrueOrNullFormField
        }
        defaults.update(kwargs)
        return super(TrueOrNullField, self).formfield(**defaults)


class IterableField(models.Field):
    @property
    def _iterable_type(self): raise NotImplementedError()

    def __init__(self, item_field_type=None, *args, **kwargs):

        # This seems bonkers, we shout at people for specifying null=True, but then do it ourselves. But this is because
        # *we* abuse None values for our own purposes (to represent an empty iterable) if someone else tries to then
        # all hell breaks loose
        if kwargs.get("null", False):
            raise RuntimeError("IterableFields cannot be set as nullable (as the datastore doesn't differentiate None vs []")

        kwargs["null"] = True

        default = kwargs.get("default", [])

        if default is not None and not callable(default):
            kwargs["default"] = lambda: self._iterable_type(default)

        if callable(item_field_type):
            item_field_type = item_field_type()

        item_field_type = item_field_type or RawField()

        self.fk_model = None
        if isinstance(item_field_type, models.ForeignKey):
            self.fk_model = item_field_type.rel.to

            if isinstance(self.fk_model, basestring):
                self.fk_model = get_model(*self.fk_model.split("."))

            if isinstance(self.fk_model._meta.pk, models.AutoField):
                item_field_type = models.PositiveIntegerField()
            else:
                raise NotImplementedError("No-autofield related PKs not yet supported")

        self.item_field_type = item_field_type

        # We'll be pretending that item_field is a field of a model
        # with just one "value" field.
        assert not hasattr(self.item_field_type, 'attname')
        self.item_field_type.set_attributes_from_name('value')

        super(IterableField, self).__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name):
        self.item_field_type.model = cls
        self.item_field_type.name = name
        super(IterableField, self).contribute_to_class(cls, name)

        # If items' field uses SubfieldBase we also need to.
        item_metaclass = getattr(self.item_field_type, '__metaclass__', None)
        if item_metaclass and issubclass(item_metaclass, models.SubfieldBase):
            setattr(cls, self.name, Creator(self))

    def _map(self, function, iterable, *args, **kwargs):
        return self._iterable_type(function(element, *args, **kwargs) for element in iterable)

    def to_python(self, value):
        if value is None:
            return self._iterable_type([])

        return self._map(self.item_field_type.to_python, value)

    def pre_save(self, model_instance, add):
        """
            Gets our value from the model_instance and passes its items
            through item_field's pre_save (using a fake model instance).
        """
        value = getattr(model_instance, self.attname)
        if value is None:
            return self._iterable_type([])

        return self._map(lambda item: self.item_field_type.pre_save(_FakeModel(self.item_field_type, item), add), value)

    def get_db_prep_save(self, value, connection):
        """
        Applies get_db_prep_save of item_field on value items.
        """

        #If the value is an empty iterable, store None
        if value == self._iterable_type([]):
            return None

        return self._map(self.item_field_type.get_db_prep_save, value,
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

        return self.item_field_type.get_db_prep_lookup(
            lookup_type, value, connection=connection, prepared=prepared)

    def get_prep_lookup(self, lookup_type, value):
        if value == self._iterable_type():
            return None
        return super(IterableField, self).get_prep_lookup(lookup_type, value)

    def validate(self, value_list, model_instance):
        """ We want to override the default validate method from django.db.fields.Field, because it
            is only designed to deal with a single choice from the user.
        """
        if not self.editable:
            # Skip validation for non-editable fields
            return

        # Validate choices
        if self.choices:
            valid_values = []
            for choice in self.choices:
                if isinstance(choice[0], (list, tuple)):
                    # this is an optgroup, so look inside it for the options
                    for optgroup_choice in choice[0]:
                        valid_values.append(optgroup_choice[0])
                else:
                    valid_values.append(choice[0])
            for value in value_list:
                if value not in valid_values:
                    # TODO: if there is more than 1 invalid value then this should show all of the invalid values
                    raise ValidationError(self.error_messages['invalid_choice'] % value)
        # Validate null-ness
        if value_list is None and not self.null:
            raise ValidationError(self.error_messages['null'])

        if not self.blank and not value_list:
            raise ValidationError(self.error_messages['blank'])

        # apply the default items validation rules
        for value in value_list:
            self.item_field_type.clean(value, model_instance)

    def formfield(self, **kwargs):
        """ If this field has choices, then we can use a multiple choice field.
            NB: The chioces must be set on *this* field, e.g. this_field = ListField(CharField(), choices=x)
            as opposed to: this_field = ListField(CharField(choices=x))
        """
        #Largely lifted straight from Field.formfield() in django.models.__init__.py
        defaults = {'required': not self.blank, 'label': capfirst(self.verbose_name), 'help_text': self.help_text}
        if self.has_default(): #No idea what this does
            if callable(self.default):
                defaults['initial'] = self.default
                defaults['show_hidden_initial'] = True
            else:
                defaults['initial'] = self.get_default()

        if getattr(self, "fk_model", None):
            #The type passed into this ListField was a ForeignKey, set the form field and
            #queryset appropriately
            form_field_class = IterableFieldModelChoiceFormField
            defaults['queryset'] = self.fk_model.objects.all()
        elif self.choices:
            form_field_class = forms.MultipleChoiceField
            defaults['choices'] = self.get_choices(include_blank=False) #no empty value on a multi-select
        else:
            form_field_class = ListFormField
        defaults.update(**kwargs)
        return form_field_class(**defaults)


class ListField(IterableField):
    def __init__(self, *args, **kwargs):
        self.ordering = kwargs.pop('ordering', None)
        if self.ordering is not None and not callable(self.ordering):
            raise TypeError("'ordering' has to be a callable or None, "
                            "not of type %r." % type(self.ordering))
        super(ListField, self).__init__(*args, **kwargs)

    def get_internal_type(self):
        return 'ListField'

    def pre_save(self, model_instance, add):
        value = super(ListField, self).pre_save(model_instance, add)

        if value and self.ordering:
            value.sort(key=self.ordering)

        return value

    @property
    def _iterable_type(self):
        return list

class SetField(IterableField):
    def get_internal_type(self):
        return 'SetField'

    @property
    def _iterable_type(self):
        return set

    def value_to_string(self, obj):
        """
        Custom method for serialization, as JSON doesn't support
        serializing sets.
        """
        return str(list(self._get_val_from_obj(obj)))


class ComputedFieldMixin(object):
    def __init__(self, func, *args, **kwargs):
        self.computer = func

        kwargs["editable"] = False

        super(ComputedFieldMixin, self).__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        value = self.computer(model_instance)
        setattr(model_instance, self.attname, value)
        return value


class ComputedCharField(ComputedFieldMixin, models.CharField):
    __metaclass__ = models.SubfieldBase


class ComputedIntegerField(ComputedFieldMixin, models.IntegerField):
    __metaclass__ = models.SubfieldBase


class ComputedTextField(ComputedFieldMixin, models.TextField):
    __metaclass__ = models.SubfieldBase


class ComputedPositiveIntegerField(ComputedFieldMixin, models.PositiveIntegerField):
    __metaclass__ = models.SubfieldBase


class ShardedCounter(list):
    def increment(self):
        idx = random.randint(0, len(self) - 1)

        with transaction.atomic():
            shard = CounterShard.objects.get(pk=self[idx])
            shard.count += 1
            shard.save()

    def decrement(self):
        #Find a non-empty shard and decrement it
        shards = self[:]
        random.shuffle(shards)
        for shard_id in shards:
            with transaction.atomic():
                shard = CounterShard.objects.get(pk=shard_id)
                if not shard.count:
                    continue
                else:
                    shard.count -= 1
                    shard.save()
                    break

    def value(self):
        shards = CounterShard.objects.filter(pk__in=self).values_list('count', flat=True)
        return sum(shards)

class ShardedCounterField(ListField):
    __metaclass__ = models.SubfieldBase

    def __init__(self, shard_count=30, *args, **kwargs):
        self.shard_count = shard_count
        super(ShardedCounterField, self).__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        value = super(ShardedCounterField, self).pre_save(model_instance, add)
        current_length = len(value)

        for i in xrange(current_length, self.shard_count):
            value.append(CounterShard.objects.create(count=0).pk)

        ret = ShardedCounter(value)
        setattr(model_instance, self.attname, ret)
        return ret

    def to_python(self, value):
        value = super(ShardedCounterField, self).to_python(value)
        return ShardedCounter(value)

    def get_prep_value(self, value):
        return value


class DescendentMixin(object):
    @classmethod
    def descendents_of(cls, instance):
        """
            This is a bit of a hack until we can drop support for 1.6 and (hopefully) reimplement this
            using custom lookups in 1.7+. We add a constraint to the where claus with the magic column of
            __ancestor__, then in the djangae database connector, we extract this constraint and remove it from the
            where before our DNF work hits.
        """
        qs = cls.objects.all()
        qs.query.where.add(
            (Constraint(None, '__ancestor__', cls._meta.pk), 'exact', instance.pk),
            'AND'
        )
        return qs

class AncestorKey(object):
    """
        Represents a key on appengine with a parent. Parent can either by an ID/Name (e.g. int/string)
        or it can be another AncestorKey or an instance (which is the usual method).
        id_or_name is the ID of the key itself.
    """

    def __init__(self, parent, id_or_name=None):
        self.parent_key = parent.pk if isinstance(parent, models.Model) else parent
        self.parent_model = parent.__class__
        self.id_or_name = id_or_name

    @property
    def parent(self):
        if not self.parent_key:
            raise AttributeError("AncestorKey has no parent")

        return self.parent_model.objects.get(pk=self.parent_key)

    def _get_datastore_key(self, this_model):
        parent_key_part = None
        if isinstance(self.parent_key, AncestorKey):
            parent_key_part = self.parent_key._get_datastore_key()
        elif isinstance(self.parent_key, (int, long, basestring)):
            parent_key_part = Key.from_path(self.parent_model._meta.db_table, self.parent_key)
        elif self.parent_key is not None:
            raise ValueError("Unhandled parent key type")

        if not self.id_or_name:
            template_key = Key.from_path(this_model._meta.db_table, 1, parent=parent_key_part)
            self.id_or_name = AllocateIds(template_key, 1)[0]

        return Key.from_path(this_model._meta.db_table, self.id_or_name, parent=parent_key_part)

    def __eq__(self, other):
        if isinstance(other, AncestorKey):
            return self.parent_key == other.parent_key and self.id_or_name == other.id_or_name
        else:
            raise TypeError("Cannot compare AncestorKey with {0}".format(type(other)))


class AncestorAutoField(models.Field):
    __metaclass__ = models.SubfieldBase

    description = "Like autofield, but allows setting an ancestor on creation"

    def __init__(self, ancestor_model, *args, **kwargs):
        self.ancestor_model = ancestor_model
        super(AncestorAutoField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        if connection.settings_dict['ENGINE'] != 'djangae.db.backends.appengine':
            raise ValueError("You can only use AncestorAutoField on the datastore")

        return "key"

    def get_prep_lookup(self, lookup_type, value):
        if lookup_type not in ('exact', 'in'):
            raise ValueError("Can only do exact lookups on ancestor fields")

        was_list = isinstance(value, (list, tuple))

        if not was_list:
            value = [ value ]

        result = []
        for v in value:
            if isinstance(v, (int, long, basestring)):
                result.append(Key.from_path(self.ancestor_model._meta.db_table, v))
            elif isinstance(v, Key):
                result.append(v)
            elif isinstance(v, AncestorKey):
                result.append(v._get_datastore_key(self.model))
            else:
                raise TypeError("Unexpected type for ancestor field lookup: {}".format(v.__class__))

        if was_list:
            return result
        return result[0]

    def get_db_prep_save(self, value, connection):
        if connection.settings_dict['ENGINE'] != 'djangae.db.backends.appengine':
            raise ValueError("You can only use AncestorAutoField on the datastore")

        return value._get_datastore_key(self.model)

    def to_python(self, value):
        if isinstance(value, AncestorKey):
            return value

        if isinstance(value, Key):
            return AncestorKey(value.parent().id_or_name(), value.id_or_name())


        return value
