#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random

from django.db import models, router
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models.fields.subclassing import Creator
from django.utils.text import capfirst
from django import forms
from djangae.forms.fields import TrueOrNullFormField, IterableFieldModelChoiceFormField, ListFormField
from django.db.models.loading import get_model

from djangae.db import transaction
from djangae.models import CounterShard
from django.utils.functional import cached_property

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
    __metaclass__ = models.SubfieldBase

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

        # If the value is an empty iterable, store None
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
            # The type passed into this ListField was a ForeignKey, set the form field and
            # queryset appropriately
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

    def get_db_prep_save(self, *args, **kwargs):
        ret = super(SetField, self).get_db_prep_save(*args, **kwargs)
        if ret:
            ret = list(ret)
        return ret

    def get_db_prep_lookup(self, *args, **kwargs):
        ret =  super(SetField, self).get_db_prep_lookup(*args, **kwargs)
        if ret:
            ret = list(ret)
        return ret

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
        # Find a non-empty shard and decrement it
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

from django.db.models.fields.related import RelatedField

class RelatedSetRel(object):
    def __init__(self, to, related_name=None, limit_choices_to=None):
        self.to = to
        self.related_name = related_name
        self.related_query_name = None
        self.field_name = None

        if limit_choices_to is None:
            limit_choices_to = {}
        self.limit_choices_to = limit_choices_to
        self.multiple = True

    def is_hidden(self):
        "Should the related object be hidden?"
        return self.related_name and self.related_name[-1] == '+'

    def set_field_name(self):
        self.field_name = self.field_name or self.to._meta.pk.name

    def get_related_field(self):
        """
        Returns the field in the to' object to which this relationship is tied
        (this is always the primary key on the target model). Provided for
        symmetry with ManyToOneRel.
        """
        return self.to._meta.pk

def create_related_set_manager(superclass, rel):

    class RelatedSetManager(superclass):
        def __init__(self, model, field, instance, reverse):
            super(RelatedSetManager, self).__init__()
            self.model = model
            self.instance = instance
            self.field = field

            if reverse:
                self.core_filters = { '%s__exact' % self.field.name: instance.pk }
            else:
                self.core_filters= {'pk__in': field.value_from_object(instance) }

        def get_queryset(self):
            db = self._db or router.db_for_read(self.instance.__class__, instance=self.instance)
            return super(RelatedSetManager, self).get_queryset().using(db)._next_is_sticky().filter(**self.core_filters)

        def add(self, value):
            if not isinstance(value, self.model):
                raise TypeError("'%s' instance expected, got %r" % (self.model._meta.object_name, value))

            if not value.pk:
                raise ValueError("Model instances must be saved before they can be added to a related set")

            self.field.value_from_object(self.instance).add(value.pk)

        def remove(self, value):
            self.field.value_from_object(self.instance).discard(value.pk)

        def clear(self):
            setattr(self.instance, self.field.attname, set())


    return RelatedSetManager

class RelatedSetObjectsDescriptor(object):
    # This class provides the functionality that makes the related-object
    # managers available as attributes on a model class, for fields that have
    # multiple "remote" values and have a ManyToManyField pointed at them by
    # some other model (rather than having a ManyToManyField themselves).
    # In the example "publication.article_set", the article_set attribute is a
    # ManyRelatedObjectsDescriptor instance.
    def __init__(self, related):
        self.related = related   # RelatedObject instance

    @cached_property
    def related_manager_cls(self):
        # Dynamically create a class that subclasses the related
        # model's default manager.
        return create_related_set_manager(
            self.related.model._default_manager.__class__,
            self.related.field.rel
        )

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        rel_model = self.related.model
        rel_field = self.related.field

        manager = self.related_manager_cls(
            model=rel_model,
            field=rel_field,
            instance=instance,
            reverse=True
        )

        return manager

    def __set__(self, obj, value):
        raise AttributeError("You can't set the reverse relation directly")

class ReverseRelatedSetObjectsDescriptor(object):
    # This class provides the functionality that makes the related-object
    # managers available as attributes on a model class, for fields that have
    # multiple "remote" values and have a ManyToManyField defined in their
    # model (rather than having another model pointed *at* them).
    # In the example "article.publications", the publications attribute is a
    # ReverseManyRelatedObjectsDescriptor instance.
    def __init__(self, m2m_field):
        self.field = m2m_field

    @cached_property
    def related_manager_cls(self):
        # Dynamically create a class that subclasses the related model's
        # default manager.
        return create_related_set_manager(
            self.field.rel.to._default_manager.__class__,
            self.field.rel.to
        )

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        manager = self.related_manager_cls(
            model=self.field.rel.to,
            field=self.field,
            instance=instance,
            reverse=False
        )

        return manager

    def __set__(self, obj, value):
        obj.__dict__[self.field.attname] = self.field.to_python([x.pk for x in value])

class RelatedSetField(RelatedField):
    requires_unique_target = False
    generate_reverse_relation = True
    empty_strings_allowed = False

    def db_type(self, connection):
        models.Field.db_type(self, connection)

    def get_internal_type(self):
        return 'SetField'

    def __init__(self, model, limit_choices_to=None, related_name=None):
        kwargs = {}
        kwargs["rel"] = RelatedSetRel(
            model,
            related_name=related_name,
            limit_choices_to=limit_choices_to
        )

        kwargs["default"] = set
        kwargs["null"] = True

        super(RelatedSetField, self).__init__(**kwargs)

    def get_attname(self):
        return '%s_ids' % self.name

    def contribute_to_class(self, cls, name):
        # To support multiple relations to self, it's useful to have a non-None
        # related name on symmetrical relations for internal reasons. The
        # concept doesn't make a lot of sense externally ("you want me to
        # specify *what* on my non-reversible relation?!"), so we set it up
        # automatically. The funky name reduces the chance of an accidental
        # clash.
        if (self.rel.to == "self" or self.rel.to == cls._meta.object_name):
            self.rel.related_name = "%s_rel_+" % name

        super(RelatedSetField, self).contribute_to_class(cls, name)

        # Add the descriptor for the m2m relation
        setattr(cls, self.name, ReverseRelatedSetObjectsDescriptor(self))


    def contribute_to_related_class(self, cls, related):
        # Internal M2Ms (i.e., those with a related name ending with '+')
        # and swapped models don't get a related descriptor.
        if not self.rel.is_hidden() and not related.model._meta.swapped:
            setattr(cls, related.get_accessor_name(), RelatedSetObjectsDescriptor(related))

    def to_python(self, value):
        if value is None:
            return set()

        return set(value)

    def get_db_prep_save(self, *args, **kwargs):
        ret = super(RelatedSetField, self).get_db_prep_save(*args, **kwargs)

        if not ret:
            return None

        if isinstance(ret, set):
            ret = list(ret)
        return ret

    def get_db_prep_lookup(self, *args, **kwargs):
        ret =  super(RelatedSetField, self).get_db_prep_lookup(*args, **kwargs)

        if not ret:
            return None

        if isinstance(ret, set):
            ret = list(ret)
        return ret

    def value_to_string(self, obj):
        """
        Custom method for serialization, as JSON doesn't support
        serializing sets.
        """
        return str(list(self._get_val_from_obj(obj)))
