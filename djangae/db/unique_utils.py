from hashlib import md5

def _unique_combinations(model, ignore_pk=False):
    unique_names = [ [ model._meta.get_field(y).name for y in x ] for x in model._meta.unique_together ]

    for field in model._meta.fields:
        if field.primary_key and ignore_pk:
            continue

        if field.unique:
            unique_names.append([field.name])

    return [ sorted(x) for x in unique_names ]

def unique_identifiers_from_entity(model, entity, ignore_pk=False, ignore_null_values=True):
    """
        Given an instance, this function returns a list of identifiers that represent
        unique field/value combinations.
    """

    UNSUPPORTED_DB_TYPES = {
        'ListField',
        'SetField',
        'DictField'
    }

    unique_combinations = _unique_combinations(model, ignore_pk)

    meta = model._meta

    identifiers = []
    for combination in unique_combinations:
        identifier = []

        include_combination = True

        for field_name in combination:
            field = meta.get_field(field_name)
            if field.get_internal_type() in UNSUPPORTED_DB_TYPES:
                raise TypeError("Unique support for {} is not yet implemented".format(field.get_internal_type()))

            if field.primary_key:
                value = entity.key().id_or_name()
            else:
                value = entity.get(field.column) #Get the value from the entity

            if value is None and ignore_null_values:
                include_combination = False

            #AppEngine max key length is 500 chars, so if the value is a string we hexdigest it to reduce the length
            #otherwise we str() it as it's probably an int or bool or something.
            value = hash(value) if isinstance(value, basestring) else str(value)
            identifier.append("{}:{}".format(field_name, value))

        if include_combination:
            identifiers.append(model._meta.db_table + "|" + "|".join(identifier))

    return identifiers