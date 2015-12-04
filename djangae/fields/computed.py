from django.db import models


class ComputedFieldMixin(object):
    def __init__(self, func, *args, **kwargs):
        self.computer = func

        kwargs["editable"] = False

        super(ComputedFieldMixin, self).__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        value = self.computer(model_instance)
        setattr(model_instance, self.attname, value)
        return value

    def deconstruct(self):
        name, path, args, kwargs = super(ComputedFieldMixin, self).deconstruct()
        args = [self.computer] + args
        del kwargs["editable"]
        return name, path, args, kwargs


class ComputedCharField(ComputedFieldMixin, models.CharField):
    pass


class ComputedIntegerField(ComputedFieldMixin, models.IntegerField):
    pass


class ComputedTextField(ComputedFieldMixin, models.TextField):
    pass


class ComputedPositiveIntegerField(ComputedFieldMixin, models.PositiveIntegerField):
    pass
