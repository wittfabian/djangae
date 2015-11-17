#STANDARD LIB
from urlparse import urlparse

# LIBRARIES
from django.contrib.auth import get_user_model, get_user, BACKEND_SESSION_KEY
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.test import TestCase
from django.test.utils import override_settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.hashers import make_password
from google.appengine.api import users

# DJANGAE
from djangae.contrib.gauth.datastore.models import GaeDatastoreUser, Group, get_permission_choices
from djangae.contrib.gauth.backends import AppEngineUserAPI
from djangae.contrib.gauth.middleware import AuthenticationMiddleware
from djangae.contrib.gauth.settings import AUTHENTICATION_BACKENDS
from djangae.contrib.gauth.utils import get_switch_accounts_url
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
        User.objects.pre_create_google_user(email)
        # Now authenticate this user via the Google Accounts API
        google_user = users.User(email=email, _user_id='111111111100000000001')
        user = backend.authenticate(google_user=google_user)
        # Check things
        self.assertEqual(user.email, email)
        self.assertIsNotNone(user.last_login)
        self.assertFalse(user.has_usable_password())

    @override_settings(ALLOW_USER_PRE_CREATION=True)
    def test_user_id_switch(self):
        """ Users sometimes login with the same email, but a different google user id. We handle those cases by
            blanking out the email on the old user object and creating a new one with the new user id.
        """
        email = 'user@customexample.com'
        old_user = users.User(email=email, _user_id='111111111100000000001')
        new_user = users.User(email=email, _user_id='111111111100000000002')
        User = get_user_model()
        backend = AppEngineUserAPI()
        # Authenticate 1st time, creating the user
        user1 = backend.authenticate(google_user=old_user)
        self.assertEqual(user1.email, email)
        self.assertTrue(user1.username.endswith('1'))
        self.assertEqual(1, User.objects.count())

        # Now another user logs in using the same email
        user2 = backend.authenticate(google_user=new_user)
        self.assertEqual(user2.email, email)
        self.assertTrue(user2.username.endswith('2'))
        self.assertEqual(2, User.objects.count())

        # The old account is kept around, but the email is blanked
        user1 = User.objects.get(pk=user1.pk)
        self.assertEqual(user1.email, None)

    @override_settings(DJANGAE_FORCE_USER_PRE_CREATION=True)
    def test_force_user_pre_creation(self):
        User = get_user_model()
        self.assertEqual(User.objects.count(), 0)
        google_user = users.User('1@example.com', _user_id='111111111100000000001')
        backend = AppEngineUserAPI()

        self.assertIsNone(backend.authenticate(google_user=google_user,))
        self.assertEqual(User.objects.count(), 0)

        # superusers don't need pre-creation of User object.
        self.assertEqual(User.objects.count(), 0)
        with sleuth.switch('google.appengine.api.users.is_current_user_admin', lambda: True):
            user = backend.authenticate(google_user=google_user,)
        self.assertEqual(User.objects.count(), 1)
        self.assertEquals(User.objects.get(), user)


@override_settings(AUTHENTICATION_BACKENDS=AUTHENTICATION_BACKENDS)
class MiddlewareTests(TestCase):
    """ Tests for the AuthenticationMiddleware. """

    def test_login(self):

        def _get_current_user():
            return users.User('1@example.com', _user_id='111111111100000000001')

        request = HttpRequest()
        SessionMiddleware().process_request(request) # Make the damn sessions work
        request.session[BACKEND_SESSION_KEY] = 'djangae.contrib.gauth.backends.AppEngineUserAPI'
        middleware = AuthenticationMiddleware()
        # Check that we're not logged in already
        user = get_user(request)
        self.assertFalse(user.is_authenticated())

        # Check that running the middleware when the Google users API doesn't know the current
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

    def test_account_switch(self):
        user1 = users.User('1@example.com', _user_id='111111111100000000001')
        user2 = users.User('2@example.com', _user_id='222222222200000000002')

        request = HttpRequest()
        SessionMiddleware().process_request(request)  # Make the damn sessions work
        request.session[BACKEND_SESSION_KEY] = 'djangae.contrib.gauth.backends.AppEngineUserAPI'
        middleware = AuthenticationMiddleware()

        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: user1):
            middleware.process_request(request)

        self.assertEqual(user1.user_id(), request.user.username)

        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: user2):
            middleware.process_request(request)

        self.assertEqual(user2.user_id(), request.user.username)

    def test_user_id_switch(self):
        """ Users sometimes login with the same email, but a different google user id. We handle those cases by
            blanking out the email on the old user object and creating a new one with the new user id.
        """
        email = 'User@example.com'
        user1 = users.User(email, _user_id='111111111100000000001')
        user2 = users.User(email, _user_id='222222222200000000002')

        User = get_user_model()
        request = HttpRequest()
        SessionMiddleware().process_request(request)  # Make the damn sessions work
        request.session[BACKEND_SESSION_KEY] = 'djangae.contrib.gauth.backends.AppEngineUserAPI'
        middleware = AuthenticationMiddleware()

        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: user1):
            middleware.process_request(request)

        self.assertEqual(1, User.objects.count())
        django_user1 = request.user
        self.assertEqual(user1.user_id(), django_user1.username)
        self.assertEqual(user1.email(), django_user1.email)

        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: user2):
            middleware.process_request(request)

        self.assertEqual(2, User.objects.count())
        django_user2 = request.user
        self.assertEqual(user2.user_id(), django_user2.username)
        self.assertEqual(user2.email(), django_user2.email)

        django_user1 = User.objects.get(pk=django_user1.pk)
        self.assertEqual(django_user1.email, None)

    @override_settings(DJANGAE_FORCE_USER_PRE_CREATION=True)
    def test_force_user_pre_creation(self):
        email = 'User@example.com'
        user1 = users.User(email, _user_id='111111111100000000001')
        with sleuth.switch('djangae.contrib.gauth.middleware.users.get_current_user', lambda: user1):
            request = HttpRequest()
            SessionMiddleware().process_request(request)  # Make the damn sessions work
            middleware = AuthenticationMiddleware()
            middleware.process_request(request)

        # We expect request.user to be AnonymousUser(), because there was no User object in the DB
        # and so with pre-creation required, authentication should have failed
        self.assertTrue(isinstance(request.user, AnonymousUser))


@override_settings(
    AUTH_USER_MODEL='djangae.GaeDatastoreUser',
    AUTHENTICATION_BACKENDS=('djangae.contrib.gauth.backends.AppEngineUserAPI',)
)
class CustomPermissionsUserModelBackendTest(TestCase):
    """
    Tests for the ModelBackend using the CustomPermissionsUser model.

    As with the ExtensionUser test, this isn't a perfect test, because both
    the User and CustomPermissionsUser are synchronized to the database,
    which wouldn't ordinary happen in production.
    """
    UserModel = GaeDatastoreUser

    def setUp(self):
        # Fix Django so that we can use our custom user model.
        # TODO: Submit a fix to Django to allow override_settings(AUTH_USER_MODEL='something') to
        # work, even if the project has already set AUTH_USER_MODEL to a custom user
        GaeDatastoreUser.objects = GaeDatastoreUser._default_manager
        GaeDatastoreUser._base_manager = GaeDatastoreUser._default_manager
        self.user = GaeDatastoreUser.objects.create(
            username='test1',
            email='test@example.com',
            password=make_password(None),
            is_active=True,
        )
        self.superuser = GaeDatastoreUser.objects.create(
            username='test2',
            email='test2@example.com',
            is_superuser=True,
            password=make_password(None),
            is_active=True,
        )

    def tearDown(self):
        GaeDatastoreUser.objects.all().delete()
        super(CustomPermissionsUserModelBackendTest, self).tearDown()

    def test_has_perm(self):
        user = self.UserModel.objects.get(pk=self.user.pk)
        self.assertEqual(user.has_perm('auth.test'), False)
        user.is_staff = True
        user.save()
        self.assertEqual(user.has_perm('auth.test'), False)
        user.is_superuser = True
        user.save()
        self.assertEqual(user.has_perm('auth.test'), True)
        user.is_staff = False
        user.is_superuser = False
        user.save()
        self.assertEqual(user.has_perm('auth.test'), False)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = False
        user.save()
        self.assertEqual(user.has_perm('auth.test'), False)

    def test_custom_perms(self):
        user = self.UserModel.objects.get(pk=self.user.pk)
        user.user_permissions = ['auth.test']
        user.save()

        # reloading user to purge the _perm_cache
        user = self.UserModel.objects.get(pk=self.user.pk)
        self.assertEqual(user.get_all_permissions() == set(['auth.test']), True)
        self.assertEqual(user.get_group_permissions(), set([]))
        self.assertEqual(user.has_module_perms('Group'), False)
        self.assertEqual(user.has_module_perms('auth'), True)
        user.user_permissions.extend(['auth.test2', 'auth.test3'])
        user.save()
        user = self.UserModel.objects.get(pk=self.user.pk)
        self.assertEqual(user.get_all_permissions(), set(['auth.test2', 'auth.test', 'auth.test3']))
        self.assertEqual(user.has_perm('test'), False)
        self.assertEqual(user.has_perm('auth.test'), True)
        self.assertEqual(user.has_perms(['auth.test2', 'auth.test3']), True)

        group = Group.objects.create(name='test_group')
        group.permissions = ['auth.test_group']
        group.save()
        user.groups = [group]
        user.save()

        user = self.UserModel.objects.get(pk=self.user.pk)
        exp = set(['auth.test2', 'auth.test', 'auth.test3', 'auth.test_group'])
        self.assertEqual(user.get_all_permissions(), exp)
        self.assertEqual(user.get_group_permissions(), set(['auth.test_group']))
        self.assertEqual(user.has_perms(['auth.test3', 'auth.test_group']), True)

        user = AnonymousUser()
        self.assertEqual(user.has_perm('test'), False)
        self.assertEqual(user.has_perms(['auth.test2', 'auth.test3']), False)

    def test_has_no_object_perm(self):
        """Regressiontest for #12462"""
        user = self.UserModel.objects.get(pk=self.user.pk)
        user.user_permissions = ['auth.test']
        user.save()

        self.assertEqual(user.has_perm('auth.test', 'object'), False)
        self.assertEqual(user.get_all_permissions('object'), set([]))
        self.assertEqual(user.has_perm('auth.test'), True)
        self.assertEqual(user.get_all_permissions(), set(['auth.test']))

    def test_get_all_superuser_permissions(self):
        """A superuser has all permissions. Refs #14795."""
        user = self.UserModel.objects.get(pk=self.superuser.pk)
        self.assertEqual(len(user.get_all_permissions()), len(get_permission_choices()))


@override_settings(
    AUTH_USER_MODEL='djangae.GaeDatastoreUser',
    AUTHENTICATION_BACKENDS=('djangae.contrib.gauth.backends.AppEngineUserAPI',)
)
class SwitchAccountsTests(TestCase):
    """ Tests for the switch accounts functionality. """

    def test_switch_accounts(self):
        gcu = 'djangae.contrib.gauth.middleware.users.get_current_user'
        final_destination = '/death/' # there's no escaping it
        switch_accounts_url = get_switch_accounts_url(next=final_destination)
        any_url = '/_ah/warmup'
        jekyll = users.User(email='jekyll@gmail.com', _user_id='1')
        hyde = users.User(email='hyde@gmail.com', _user_id='2')

        # we start our scenario with the user logged in
        with sleuth.switch(gcu, lambda: jekyll):
            response = self.client.get(any_url)
            # Check that the user is logged in
            expected_user_query = GaeDatastoreUser.objects.filter(username=jekyll.user_id())
            self.assertEqual(len(expected_user_query), 1)
            self.assertEqual(int(self.client._session()['_auth_user_id']), expected_user_query[0].pk)
            # Now call the switch_accounts view, which should give us a redirect to the login page
            response = self.client.get(switch_accounts_url, follow=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['location'], users.create_login_url(switch_accounts_url))
            # In tests, we don't have dev_appserver fired up, so we can't actually call the login
            # URL, but let's suppose that the user wasn't logged into multiple accounts at once
            # and so the login page redirected us straight back to the switch_accounts view.
            # It should detect this, and should now redirect us to the log*out* URL with a
            # destination of the log*in* URL
            response = self.client.get(switch_accounts_url)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response['location'],
                users.create_logout_url(users.create_login_url(switch_accounts_url))
            )
            # And now we have to emulate the scenario that we have now logged in with a different
            # account, so re-mock that
        with sleuth.switch(gcu, lambda: hyde):
            # Now that we're logged in as a different user, we expect request.user to get set to
            # the equivalent Django user and to be redirected to our final destination
            response = self.client.get(switch_accounts_url)
            redirect_path = urlparse(response['location']).path # it has the host name as well
            self.assertEqual(redirect_path, final_destination)
            expected_user_query = GaeDatastoreUser.objects.filter(username=hyde.user_id())
            self.assertEqual(len(expected_user_query), 1)
            self.assertEqual(int(self.client._session()['_auth_user_id']), expected_user_query[0].pk)
