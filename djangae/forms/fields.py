from django import forms

class TrueOrNullFormField(forms.Field):
    def clean(self, value):
        if value:
            return True
        return None


class ListWidget(forms.TextInput):
    """ A widget for being able to display a ListField. """

    def render(self, name, value, attrs=None):
        if isinstance(value, (list, tuple)):
            value = u', '.join([unicode(v) for v in value])
        return super(ListWidget, self).render(name, value, attrs)

    def value_from_datadict(self, data, files, name):
        """ Given a dictionary of data and this widget's name, returns the value
            of this widget. Returns None if it's not provided.
        """
        value = data.get(name, '')
        return [v.strip() for v in value.split(',') if len(v.strip()) > 0]


class ListFormField(forms.Field):
    """ A form field for being able to display a ListField. """

    widget = ListWidget
    delimiter = ','

    def clean(self, value):
        if value:
            if isinstance(value, (list, tuple)):
                self._check_values_against_delimiter(value)
                return value
            return [v.strip() for v in value.split(',') if len(v.strip()) > 0]
        return None

    def _check_values_against_delimiter(self, values):
        delimiter = self.delimiter  # faster
        for value in values:
            assert delimiter not in value
