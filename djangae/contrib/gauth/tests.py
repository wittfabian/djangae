#STANDARD LIB

# LIBRARIES
from django.contrib.auth import get_user_model
from django.test import TestCase
from google.appengine.api import users

# DJANGAE
from djangae.contrib.auth.backends import AppEngineUserAPI


class BackendTests(TestCase):
    """ Tests for the AppEngineUserAPI auth backend. """

    def test_invalid_credentials_cause_typeerror(self):
        """ If the `authenticate` method is passed credentials which it doesn't understand then
            Django expects it to raise a TypeError.
        """
        backend = AppEngineUserAPI()
        credentials = {'username': 'ted', 'password': 'secret'}
        self.assertRaises(TypeError, backend.authenticate, **credentials)

    def test_authenticate_creates_user_object(self):
        """ If `authenticate` is called with valid credentials then a User object should be created
        """
        User = get_user_model()
        self.assertEqual(User.objects.count(), 0)
        google_user = users.User('1@example.com', _user_id='111111111100000000001')
        backend = AppEngineUserAPI()
        user = backend.authenticate(google_user=google_user,)
        self.assertEqual(user.email, '1@example.com')
        self.assertEqual(User.objects.count(), 1)
        # Calling authenticate again with the same credentials should not create another user
        user2 = backend.authenticate(google_user=google_user)
        self.assertEqual(user.pk, user2.pk)
