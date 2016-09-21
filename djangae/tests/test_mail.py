# THIRD PARTY
from django.core.mail import send_mail
from django.test import override_settings
from google.appengine.api.app_identity import get_application_id

# DJANGAE
from djangae.contrib import sleuth
from djangae.test import TestCase


class EmailBackendTests(TestCase):

    def _get_valid_sender_address(self):
        """ Return an email address which will be allowed as a 'from' address for the current App
            Engine app.
        """
        return "example@%s.appspotmail.com" % get_application_id()

    @override_settings(EMAIL_BACKEND='djangae.mail.EmailBackend')
    def test_send_email(self):
        """ Test that sending an email using Django results in the email being sent through App
            Engine.
        """
        with sleuth.watch('djangae.mail.aeemail.EmailMessage.send') as gae_send:
            send_mail("Subject", "Hello", self._get_valid_sender_address(), ["1@example.com"])
            self.assertTrue(gae_send.called)

    @override_settings(EMAIL_BACKEND='djangae.mail.AsyncEmailBackend')
    def test_send_email_deferred(self):
        """ Test that sending an email using Django results in the email being sent through App
            Engine.
        """
        with sleuth.watch('djangae.mail.aeemail.EmailMessage.send') as gae_send:
            send_mail("Subject", "Hello", self._get_valid_sender_address(), ["1@example.com"])
            self.process_task_queues()
            self.assertTrue(gae_send.called)
