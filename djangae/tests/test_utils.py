from django.db import models
from djangae.contrib import sleuth
from djangae.test import TestCase, inconsistent_db
from djangae.utils import get_next_available_port
from djangae.db.consistency import ensure_instance_included


class AvailablePortTests(TestCase):

    def test_get_next_available_port(self):
        url = "127.0.0.1"
        port = 8081
        self.assertEquals(8081, get_next_available_port(url, port))
        with sleuth.switch("djangae.utils.port_is_open",
                lambda *args, **kwargs: False if args[1] < 8085 else True):
            self.assertEquals(8085, get_next_available_port(url, port))


class EnsureCreatedModel(models.Model):
    field1 = models.IntegerField()

    class Meta:
        app_label = "djangae"

    def __unicode__(self):
        return u"PK: {}, field1 {}".format(self.pk, self.field1)

class EnsureCreatedTests(TestCase):

    def test_basic_usage(self):
        for i in xrange(5):
            EnsureCreatedModel.objects.create(
                pk=i + 1,
                field1=i
            )

        with inconsistent_db():
            new_instance = EnsureCreatedModel.objects.create(
                pk=7,
                field1=3
            )

            qs = EnsureCreatedModel.objects.all()
            self.assertEqual(5, len(qs)) # Make sure we don't get the new instance
            self.assertEqual(6, len(ensure_instance_included(qs, new_instance.pk))) # Make sure we do
            self.assertEqual(5, len(ensure_instance_included(qs[:5], new_instance.pk))) # Make sure slicing returns the right number

            evaled = [ x for x in ensure_instance_included(qs.order_by("field1"), new_instance.pk) ]
            self.assertEqual(new_instance, evaled[4]) # Make sure our instance is correctly positioned

            evaled = [ x for x in ensure_instance_included(qs.order_by("-field1"), new_instance.pk) ]
            self.assertEqual(new_instance, evaled[1], evaled) # Make sure our instance is correctly positioned

        # Now we're in consistent land!
        self.assertTrue(EnsureCreatedModel.objects.filter(pk=7)[:1])
        self.assertEqual(6, len(ensure_instance_included(qs, new_instance.pk)))
