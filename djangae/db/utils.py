#STANDARD LIB
from datetime import datetime
from decimal import Decimal
import warnings

#LIBRARIES
from django.conf import settings
from django.db.backends.util import format_number
from django.db import IntegrityError
from django.utils import timezone
from google.appengine.api import datastore
from google.appengine.api.datastore import Key

#DJANGAE
from djangae.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES


def make_timezone_naive(value):
    if value is None:
        return None

    if timezone.is_aware(value):
        if settings.USE_TZ:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            raise ValueError("Djangae backend does not support timezone-aware datetimes when USE_TZ is False.")
    return value


def decimal_to_string(value, max_digits=16, decimal_places=0):
    """
    Converts decimal to a unicode string for storage / lookup by nonrel
    databases that don't support decimals natively.

    This is an extension to `django.db.backends.util.format_number`
    that preserves order -- if one decimal is less than another, their
    string representations should compare the same (as strings).

    TODO: Can't this be done using string.format()?
          Not in Python 2.5, str.format is backported to 2.6 only.
    """

    # Handle sign separately.
    if value.is_signed():
        sign = u'-'
        value = abs(value)
    else:
        sign = u''

    # Let Django quantize and cast to a string.
    value = format_number(value, max_digits, decimal_places)

    # Pad with zeroes to a constant width.
    n = value.find('.')
    if n < 0:
        n = len(value)
    if n < max_digits - decimal_places:
        value = u'0' * (max_digits - decimal_places - n) + value
    return sign + value


def normalise_field_value(value):
    """ Converts a field value to a common type/format to make comparable to another. """
    if isinstance(value, datetime):
        return make_timezone_naive(value)
    elif isinstance(value, Decimal):
        return decimal_to_string(value)
    return value


def get_datastore_kind(model):
    return model._meta.db_table

    # for parent in model._meta.parents.keys():
    #     if not parent._meta.parents and not parent._meta.abstract:
    #         db_table = parent._meta.db_table
    #         break
    # return db_table


def get_prepared_db_value(connection, instance, field, raw=False):
    value = getattr(instance, field.attname) if raw else field.pre_save(instance, instance._state.adding)

    value = field.get_db_prep_save(
        value,
        connection = connection
    )

    value = connection.ops.value_for_db(value, field)

    return value

def django_instance_to_entity(connection, model, fields, raw, instance):
    # uses_inheritance = False
    inheritance_root = model
    db_table = get_datastore_kind(model)

    def value_from_instance(_instance, _field):
        value = get_prepared_db_value(connection, _instance, _field, raw)

        if (not _field.null and not _field.primary_key) and value is None:
            raise IntegrityError("You can't set %s (a non-nullable "
                                     "field) to None!" % _field.name)

        is_primary_key = False
        if _field.primary_key and _field.model == inheritance_root:
            is_primary_key = True

        return value, is_primary_key

    # if [ x for x in model._meta.get_parent_list() if not x._meta.abstract]:
    #     #We can simulate multi-table inheritance by using the same approach as
    #     #datastore "polymodels". Here we store the classes that form the heirarchy
    #     #and extend the fields to include those from parent models
    #     classes = [ model._meta.db_table ]
    #     for parent in model._meta.get_parent_list():
    #         if not parent._meta.parents:
    #             #If this is the top parent, override the db_table
    #             inheritance_root = parent

    #         classes.append(parent._meta.db_table)
    #         for field in parent._meta.fields:
    #             fields.append(field)

    #     uses_inheritance = True


    #FIXME: This will only work for two levels of inheritance
    # for obj in model._meta.get_all_related_objects():
    #     if model in [ x for x in obj.model._meta.parents if not x._meta.abstract]:
    #         try:
    #             related_obj = getattr(instance, obj.var_name)
    #         except obj.model.DoesNotExist:
    #             #We don't have a child attached to this field
    #             #so ignore
    #             continue

    #         for field in related_obj._meta.fields:
    #             fields.append(field)

    field_values = {}
    primary_key = None

    # primary.key = self.model._meta.pk
    for field in fields:
        value, is_primary_key = value_from_instance(instance, field)
        if is_primary_key:
            primary_key = value
        else:
            field_values[field.column] = value

        #Add special indexed fields
        for index in special_indexes_for_column(model, field.column):
            indexer = REQUIRES_SPECIAL_INDEXES[index]
            field_values[indexer.indexed_column_name(field.column)] = indexer.prep_value_for_database(value)

    kwargs = {}
    if primary_key:
        if isinstance(primary_key, int):
            kwargs["id"] = primary_key
        elif isinstance(primary_key, basestring):
            if len(primary_key) >= 500:
                warnings.warn("Truncating primary key"
                    " that is over 500 characters. THIS IS AN ERROR IN YOUR PROGRAM.",
                    RuntimeWarning
                )
                primary_key = primary_key[:500]

            kwargs["name"] = primary_key
        else:
            raise ValueError("Invalid primary key value")
        #If the model has a concrete parent then we must specify the parent object's Key.
        #Note that the a concrete parent's pk is always the same.
        concrete_parents = get_concrete_parent_models(model)
        if concrete_parents:
            kwargs["parent"] = Key.from_path(get_datastore_kind(concrete_parents[0]), primary_key)

    entity = datastore.Entity(db_table, **kwargs)
    entity.update(field_values)

    # if uses_inheritance:
    #     entity["class"] = classes

    #print inheritance_root.__name__ if inheritance_root else "None", model.__name__, entity
    return entity


def get_datastore_key(model, pk):
    """ Return a datastore.Key for the given model and primary key.
        Takes into account the fact that models with a concrete (non-abstract) parent model
        should include the parent object's key as an datastore ancestor.
    """
    concrete_parents = get_concrete_parent_models(model)
    if concrete_parents:
        #Note that parent objects always share the same pk
        parent = Key.from_path(get_datastore_kind(concrete_parents[0]), pk)
    else:
        parent = None
    return Key.from_path(get_datastore_kind(model), pk, parent=parent)


def get_concrete_parent_models(model):
    """ Given a Django model class, return a list of non-abstract parent models. """
    return [x for x in model._meta.get_parent_list() if not x._meta.abstract]


class MockInstance(object):
    """
        This creates a mock instance for use when passing a datastore entity
        into get_prepared_db_value. This is used when performing updates to prevent a complete
        conversion to a Django instance before writing back the entity
    """

    def __init__(self, field, value, is_adding=False):
        class State:
            adding = is_adding

        self._state = State()
        self.field = field
        self.value = value

    def __getattr__(self, attr):
        if attr == self.field.attname:
            return self.value
        return super(MockInstance, self).__getattr__(attr)
