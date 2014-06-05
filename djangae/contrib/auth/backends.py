from django.contrib.auth.models import User, UserPermissionStorage

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

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _get_ups_attr(self, attr, user_obj, obj=None):
        """ Collects either `all_permissions` or `group_permissions` from all matching
            UserPermissionStorage objects (the specific UPS for the given row/obj
            and the generic global UPS of the user).
        """
        perms = []
        for ups in UserPermissionStorage.get_for(user_obj, obj=obj):
            perms.extend(getattr(ups, attr))

        return perms

    def get_group_permissions(self, user_obj, obj=None, user_perm_obj=None):
        """ Returns a set of permission strings that this user has through his/her groups. """
        return self._get_ups_attr('group_permissions', user_obj, obj=obj)

    def get_all_permissions(self, user_obj, obj=None):
        #FIXME: the caching attr should take into account the obj param!
        if not hasattr(user_obj, '_perm_cache'):
            user_obj._perm_cache = set(self._get_ups_attr('all_permissions', user_obj, obj=obj))
        return user_obj._perm_cache

    def has_perm(self, user_obj, perm, obj=None):
        return perm in self.get_all_permissions(user_obj, obj=obj)

    def has_module_perms(self, user_obj, app_label):
        """
        Returns True if user_obj has any permissions in the given app_label.
        Note that in Engage we use this to check permissions on a section of the CMS,
        e.g. 'content', 'agents', rather than an actual django app.
        """
        for perm in self.get_all_permissions(user_obj):
            if perm[:perm.index('.')] == app_label:
                return True
        return False
