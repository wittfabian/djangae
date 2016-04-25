# LIBRARIES
from django import forms

# DJANGAE
from djangae.test import TestCase
from djangae.tests.test_db_fields import JSONFieldModel


class JSONModelForm(forms.ModelForm):
    class Meta:
        model = JSONFieldModel
        fields = ['json_field']


class JSONFieldFormsTest(TestCase):

    def test_json_data_is_python_after_cleaning(self):
        """ In the forms' `cleaned_data`, the json_field data should be python, rather than still
            a string.
        """
        data = dict(json_field="""{"cats": "awesome", "dogs": 46234}""")
        form = JSONModelForm(data)
        assert form.is_valid()  # Sanity, and to trigger cleaned_data
        expected_data = {"cats": "awesome", "dogs": 46234}
        self.assertEqual(form.cleaned_data['json_field'], expected_data)
