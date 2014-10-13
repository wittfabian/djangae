#STANDARD LIB

# LIBRARIES
from django.contrib.auth import get_user_model, get_user
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.test import TestCase
from django.test.utils import override_settings
from google.appengine.api import users

# DJANGAE
from djangae.contrib.gauth.backends import AppEngineUserAPI
from djangae.contrib.gauth.middleware import AuthenticationMiddleware
from djangae.contrib.gauth.settings import AUTHENTICATION_BACKENDS
from djangae.contrib import sleuth


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

    @override_settings(ALLOW_USER_PRE_CREATION=True)
    def test_user_pre_creation(self):
        """ User objects for Google-Accounts-based users should be able to be pre-created in DB and
            then matched by email address when they log in.
        """
        User = get_user_model()
        backend = AppEngineUserAPI()
        email = '1@example.com'
        # Pre-create our user
        user = User.objects.pre_create_google_user(email)
        # Now authenticate this user via the Google Accounts API
        google_user = users.User(email=email, _user_id='111111111100000000001')
        user = backend.authenticate(google_user=google_user)
        # Check things
        self.assertEqual(user.email, email)
        self.assertIsNotNone(user.last_login)
        self.assertFalse(user.has_usable_password())


@override_settings(AUTHENTICATION_BACKENDS=AUTHENTICATION_BACKENDS)
class MiddlewareTests(TestCase):
    """ Tets for the AuthenticationMiddleware. """

    def test_login(self):

        def _get_current_user():
            return users.User('1@example.com', _user_id='111111111100000000001')

        request = HttpRequest()
        SessionMiddleware().process_request(request) # Make the damn sessions work
        middleware = AuthenticationMiddleware()
        # Check that we're not logged in already
        user = get_user(request)
        self.assertFalse(user.is_authenticated())

        # Check that running the middelware when the Google users API doesn't know the current
        # user still leaves us as an anonymous users.
        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: None):
            middleware.process_request(request)

        # Check that the middleware successfully logged us in
        user = get_user(request)
        self.assertFalse(user.is_authenticated())

        # Now check that when the Google users API *does* know who we are, that we are logged in.
        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', _get_current_user):
            middleware.process_request(request)

        # Check that the middleware successfully logged us in
        user = get_user(request)
        self.assertTrue(user.is_authenticated())
        self.assertEqual(user.email, '1@example.com')
        self.assertEqual(user.username, '111111111100000000001')


