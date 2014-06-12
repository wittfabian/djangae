from djangae.contrib.auth.models import User

class AppEngineUserAPI(object):
    """
        A custom Django authentication backend, which lets us authenticate against the Google
        users API
    """

    supports_anonymous_user = True

    def authenticate(self, **credentials):
        """
        Handles authentication of a user from the given credentials.
        Credentials must be a combination of 'request' and 'google_user'.
         If any other combination of credentials are given then we raise a TypeError, see authenticate() in django.contrib.auth.__init__.py.
        """

        if len(credentials) != 2:
            raise TypeError()

        request = credentials.get('request', None)
        google_user = credentials.get('google_user', None)

        if request and google_user:
            username = google_user.user_id()
            email = google_user.email().lower()
            try:
                user = User.objects.get(username=username)

            except User.DoesNotExist:
                user = User.objects.create_user(username, email)

            return user
        else:
            raise TypeError()  # Django expects to be able to pass in whatever credentials it has, and for you to raise a TypeError if they mean nothing to you
