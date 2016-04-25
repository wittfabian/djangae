# LIBRARIES
from bs4 import BeautifulSoup
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

    def test_json_data_is_rendered_as_json_in_html_form(self):
        """ When the form renders the <textarea> with the JSON in it, it should have been through
            json.dumps, and should not just be repr(python_thing).
        """
        instance = JSONFieldModel(json_field={u'name': 'Lucy', 123: 456})
        form = JSONModelForm(instance=instance)
        html = form.as_p()
        soup = BeautifulSoup(html, "html.parser")
        # Now we want to check that our value was rendered as JSON.
        # So the key 123 should have been converted to a string key of "123"
        textarea = soup.find("textarea").text
        self.assertTrue('"123"' in textarea)
