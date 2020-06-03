from djangae.test import TestCase
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.test import override_settings
from django.urls import (
    include,
    path,
)


class PermissionTests(TestCase):
    pass


@login_required
def login(request):
    return HttpResponse("OK")


urlpatterns = [
    path("login_required", login),
    path("googleauth", include("djangae.contrib.googleauth"))
]


@override_settings(ROOT_URLCONF=__name__)
class OAuthTests(TestCase):

    def test_redirect_to_authorization_url(self):
        """
            Access to a page that is login_required
            should redirect to the authorization url
        """

        response = self.client.get("/login_required")
        self.assertEqual(302, response.status_code)
        import ipdb; ipdb.set_trace()
        pass

    def test_oauth_callback_creates_session(self):
        """
            Should create an oauth session (if valid)
            and then redirect to the correct URL.

            Middleware should take care of authenticating the
            Django session
        """
        pass

    def test_login_checks_scope_whitelist(self):
        """
            Accessing the oauth login page with
            additional scopes in the GET param
            should only work for whitelisted scopes
        """
        pass

    def test_login_respects_additional_scopes(self):
        """
            Accessing the oauth login page with additional
            scopes in the GET param should forward those
            to the authorization url
        """
        pass


class OAuth2CallbackTests(TestCase):

    def test_invalid_token_raises_404(self):
        pass

    def test_scopes_must_be_whitelisted(self):
        pass

    def test_callback_sets_session_key(self):
        pass


class OAuthScopesRequiredTests(TestCase):
    def test_oauth_scopes_required_redirects_to_login(self):
        pass

    def test_oauth_scopes_required_redirects_for_additional_scopes(self):
        pass


class AuthBackendTests(TestCase):
    def test_valid_oauth_session_creates_django_session(self):
        pass

    def test_invalid_oauth_session_logs_out_django(self):
        pass

    def test_backend_does_nothing_if_authed_with_different_backend(self):
        """
            If you have the model backend and oauth backend (for example)
            then we don't log someone out if they authed with the model
            backend
        """
        pass
