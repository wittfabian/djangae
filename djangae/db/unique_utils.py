from hashlib import md5

def _unique_combinations(model):
    unique_names = [ [ model._meta.get_field(y).name for y in x ] for x in model._meta.unique_together ]

    for field in model._meta.fields:
        if field.unique:
            unique_names.append([field.name])

    return [ sorted(x) for x in unique_names ]

def unique_identifiers_from_entity(model, entity):
    """
        Given an instance, this function returns a list of identifiers that represent
        unique field/value combinations.
    """

    UNSUPPORTED_DB_TYPES = {
        'ListField',
        'SetField',
        'DictField',
        'TextField'
    }

    unique_combinations = _unique_combinations(model)

    meta = model._meta

    identifiers = []
    for combination in unique_combinations:
        identifier = []
        for field_name in combination:
            field = meta.get_field(field_name)
            if field.get_internal_type() in UNSUPPORTED_DB_TYPES:
                raise TypeError("Unique support for {} is not yet implemented".format(field.get_internal_type()))

            if field.primary_key:
                value = entity.key().id_or_name()
            else:
                value = getattr(entity, field.column, None) #Get the value from the entity

            #AppEngine max key length is 500 chars, so if the value is a string we hexdigest it to reduce the length
            #otherwise we str() it as it's probably an int or bool or something.
            value = md5(value).hexdigest() if isinstance(value, basestring) else str(value)
            identifier.append("{}:{}".format(field_name, value))
        identifiers.append("|".join(identifier))
    return identifiers