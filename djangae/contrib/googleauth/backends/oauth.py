from django.contrib.auth.backends import BaseBackend
from ..models import User, UserPermission, Group, _OAUTH_USER_SESSION_SESSION_KEY, OAuthUserSession


class OAuthBackend(BaseBackend):
    def authenticate(self, request, **kwargs):
        oauth_session_id = request.session.get(_OAUTH_USER_SESSION_SESSION_KEY)

        user = None
        if oauth_session_id:
            oauth_session = OAuthUserSession.objects.filter(
                pk=oauth_session_id
            ).first()

            if oauth_session and oauth_session.is_valid():
                # Valid session? Get or create the user by their email address
                user, created = User.objects.get_or_create(
                    email=oauth_session.email_address,
                )

            # Delete the session key now that it's been used, we don't
            # need it now a User has been created (if the session was valid)
            del request.session[_OAUTH_USER_SESSION_SESSION_KEY]

        return user

    def user_can_authenticate(self, user):
        return user.is_active

    def get_user(self, user_id):
        try:
            user = User._default_manager.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

    def get_user_permissions(self, user_obj, obj=None):
        qs = UserPermission.objects.filter(
            user_id=user_obj.pk
        ).values_list("permission", flat=True)

        if obj:
            qs = qs.filter(obj_id=obj.pk)

        return list(qs)

    def get_group_permissions(self, user_obj, obj=None):
        perms = set()
        qs = Group.objects.filter(users__contains=user_obj)
        for group in qs:
            perms.update(group.permissions)

        return list(perms)
