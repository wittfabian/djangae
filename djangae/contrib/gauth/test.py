""" Utilities for assisting with tests. """

# STANDARD LIB
import contextlib
import random
import string

# THIRD PARTY
from django.contrib.auth import get_user_model
from google.appengine.api import users

# DJANGAE
from djangae.contrib import sleuth


class LoginAsUser(object):
    """ Context manager for tests to allow being logged in as a user.
        Works with the djangae.contrib.gauth authentication backend.
        Allows a User object to be passed in, or will create one for you using any other kwargs
        that you pass.
    """

    def __init__(self, user=None, **user_kwargs):
        if not user:
            user = self.make_user(**user_kwargs)
        self.user = user
        self.gae_user = users.User(email=user.email)

    def __call__(self):
        patches = []
        patches.append(sleuth.fake("djangae.contrib.gauth.middleware.users.get_current_user", self.gae_user))
        if self.user.is_superuser:
            # If the user is set to be a superuser then we also need to patch App Engine's
            # is_current_user_admin function, because djangae.contrib.gauth's auth backend syncs
            # the is_superuser field to the value that is_current_user_admin() returns.
            patches.append(sleuth.fake("djangae.contrib.gauth.middleware.users.is_current_user_admin", True))
        with contextlib.nested(*patches):
            yield

    def make_user(self, **kwargs):
        """ Method which can be overridden by subclasses to customise user creation, e.g. by using
            a model generator such as Model Mommy or Factory Boy.
        """
        model = get_user_model()
        username = kwargs.pop("username", None)
        email = kwargs.pop("username", None) or self._make_random_email_address()
        return model.objects.create_user(username, email=email, **kwargs)

    def _make_random_email_address():
        username = "".join(random.sample(string.letters), random.randint(5, 10))
        return username + "@example.com"


def login_as_user(**kwargs):
    context_manager = LoginAsUser(**kwargs)
    return contextlib.contextmanager(context_manager)
