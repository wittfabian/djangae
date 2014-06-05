from django import forms
from django.forms.models import ModelChoiceIterator
from django.utils.encoding import smart_unicode

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
        delimiter = self.delimiter #faster
        for value in values:
            assert delimiter not in value

class IterableFieldModelChoiceFormField(forms.Field):
    """
        Like Django's ModelChoiceField for ListFields when the ListField is a list of IDs to instances
        You must specify the source queryset, like Django's modelchoicefield does
    """
    def __init__(self, choices=None, queryset=None, *args, **kwargs):
        if "widget" not in kwargs:
            kwargs['widget'] = ListWidget()

        self.empty_label = None
        self.cache_choices = None

        if choices:
            self.choices = choices

        if queryset:
            self.queryset = queryset

        super(IterableFieldModelChoiceFormField, self).__init__(*args, **kwargs)

    def prepare_value(self, value):
        if hasattr(value, '_meta'):
            return value.pk

        return super(IterableFieldModelChoiceFormField, self).prepare_value(value)

    # this method will be used to create object labels by the QuerySetIterator.
    # Override it to customize the label.
    def label_from_instance(self, obj):
        """
        This method is used to convert objects into strings; it's used to
        generate the labels for the choices presented by this object. Subclasses
        can override this method to customize the display of the choices.
        """
        return smart_unicode(obj)

    def _get_queryset(self):
        return self._queryset

    def _set_queryset(self, queryset):
        self._queryset = queryset
        if isinstance(self.widget, ListWidget):
            self.widget = forms.SelectMultiple(
                choices=self.choices
            )
        else:
            self.widget.choices = self.choices

    queryset = property(_get_queryset, _set_queryset)

    def _get_choices(self):
        # If self._choices is set, then somebody must have manually set
        # the property self.choices. In this case, just return self._choices.
        if hasattr(self, '_choices'):
            return self._choices

        # Otherwise, execute the QuerySet in self.queryset to determine the
        # choices dynamically. Return a fresh ModelChoiceIterator that has not been
        # consumed. Note that we're instantiating a new ModelChoiceIterator *each*
        # time _get_choices() is called (and, thus, each time self.choices is
        # accessed) so that we can ensure the QuerySet has not been consumed. This
        # construct might look complicated but it allows for lazy evaluation of
        # the queryset.
        return ModelChoiceIterator(self)

    def _set_choices(self, choices):
        if hasattr(self, "_choices"):
            self._choices = choices
            self.widget = forms.SelectMultiple(
                choices = self._choices
            )
        else:
            self._choices = choices
            self.widget.choices = choices

    choices = property(_get_choices, _set_choices)