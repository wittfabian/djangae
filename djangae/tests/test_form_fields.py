# LIBRARIES
from bs4 import BeautifulSoup
from django import forms
from django.db import models

# DJANGAE
from djangae.fields import ListField, RelatedListField
from djangae.test import TestCase
from djangae.tests.test_db_fields import JSONFieldModel, NullableJSONFieldModel


class JSONModelForm(forms.ModelForm):
    class Meta:
        model = JSONFieldModel
        fields = ['json_field']


class NullableJSONModelForm(forms.ModelForm):
    class Meta:
        model = NullableJSONFieldModel
        fields = ['json_field']


class BlankableListFieldModel(models.Model):
    list_field = ListField(models.CharField(max_length=1), blank=True)


class ListFieldForm(forms.ModelForm):
    class Meta:
        model = BlankableListFieldModel
        fields = ['list_field']


class CharFieldModel(models.Model):
    """Simple model we can reference as the related model in RelatedListField."""
    string_field = models.CharField(max_length=2)


class RelatedListFieldModel(models.Model):
    related_list_field = RelatedListField(CharFieldModel)


class RelatedListFieldForm(forms.ModelForm):
    class Meta:
        model = RelatedListFieldModel
        fields = ['related_list_field']


class RequiredRelatedListFieldForm(forms.ModelForm):

    class Meta:
        model = RelatedListFieldModel
        fields = ['related_list_field']

    def __init__(self, *args, **kwargs):
        super(RequiredRelatedListFieldForm, self).__init__(*args, **kwargs)
        self.fields['related_list_field'].required = True


class JSONFieldFormsTest(TestCase):

    def test_empty_string_submission(self):
        data = dict(json_field="")
        form = JSONModelForm(data)
        assert form.is_valid()  # Sanity, and to trigger cleaned_data
        expected_data = None
        self.assertEqual(form.cleaned_data['json_field'], expected_data)

    def test_nullable_field(self):
        data = dict(json_field="")
        form = NullableJSONModelForm(data)
        assert form.is_valid()  # Sanity, and to trigger cleaned_data
        expected_data = None
        self.assertEqual(form.cleaned_data['json_field'], expected_data)

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


class ListFieldFormsTest(TestCase):

    def test_save_empty_value_from_form(self):
        """ Submitting an empty value in the form should save an empty list. """
        data = dict(list_field="")
        form = ListFieldForm(data)
        self.assertTrue(form.is_valid())
        obj = form.save()
        self.assertEqual(obj.list_field, [])


class OrderedModelMultipleChoiceField(TestCase):

    def test_order_retained(self):
        """
        Assert that when a list of values are saved, their order is preserved.
        """
        instance_one, instance_two, instance_three = [
            CharFieldModel.objects.create(
                string_field=str(x)
            ) for x in xrange(3)
        ]
        data = dict(related_list_field=[
            instance_two.pk, instance_three.pk, instance_one.pk]
        )
        form = RelatedListFieldForm(data)
        self.assertTrue(form.is_valid())
        obj = form.save()

        self.assertEqual(
            obj.related_list_field_ids,
            [instance_two.pk, instance_three.pk, instance_one.pk]
        )

    def test_validation_still_performed(self):
        """
        Assert the normal validation of the field value occurs despite
        adding extra logic to the clean method.
        """
        data = dict(related_list_field=[])
        form = RelatedListFieldForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('related_list_field', form.errors)
