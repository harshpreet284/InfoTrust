from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpRequest
from django.test import TestCase
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth

from claims.permissions import AdminEndpointAuth, is_admin_user


class TestIsAdminUser(TestCase):
    def test_is_admin_user_none_returns_false(self):
        """Pass None, verify null-safe return of False."""
        self.assertFalse(is_admin_user(None))

    def test_is_admin_user_missing_attributes_returns_false(self):
        """Pass an object lacking role and is_superuser attributes, verify safe False return."""
        self.assertFalse(is_admin_user(object()))

    def test_is_admin_user_normal_user_returns_false(self):
        """Pass a standard user with role='USER' and is_superuser=False, verify returns False."""
        user = SimpleNamespace(role="USER", is_superuser=False)
        self.assertFalse(is_admin_user(user))

    def test_is_admin_user_app_admin_returns_true(self):
        """Pass an application admin with role='ADMIN' and is_superuser=False, verify returns True."""
        user = SimpleNamespace(role="ADMIN", is_superuser=False)
        self.assertTrue(is_admin_user(user))

    def test_is_admin_user_superuser_with_user_role_returns_true(self):
        """Pass a superuser with role='USER' and is_superuser=True, verify returns True."""
        user = SimpleNamespace(role="USER", is_superuser=True)
        self.assertTrue(is_admin_user(user))

    def test_is_admin_user_superuser_with_admin_role_returns_true(self):
        """Pass a superuser with role='ADMIN' and is_superuser=True, verify returns True."""
        user = SimpleNamespace(role="ADMIN", is_superuser=True)
        self.assertTrue(is_admin_user(user))


class TestAdminEndpointAuth(TestCase):
    def test_admin_endpoint_auth_rejects_non_admin_with_403(self):
        """Verify AdminEndpointAuth raises HttpError(403) when JWTAuth resolves a non-admin user."""
        non_admin_user = SimpleNamespace(role="USER", is_superuser=False)
        with patch.object(JWTAuth, "authenticate", return_value=non_admin_user):
            auth = AdminEndpointAuth()
            with self.assertRaises(HttpError) as ctx:
                auth.authenticate(HttpRequest(), "fake_token")
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertEqual(
                str(ctx.exception), "You do not have permission to perform this action."
            )

    def test_admin_endpoint_auth_allows_admin_user(self):
        """Verify AdminEndpointAuth returns the user when JWTAuth resolves an admin user."""
        admin_user = SimpleNamespace(role="ADMIN", is_superuser=False)
        with patch.object(JWTAuth, "authenticate", return_value=admin_user):
            auth = AdminEndpointAuth()
            result = auth.authenticate(HttpRequest(), "fake_token")
            self.assertIs(result, admin_user)

    def test_admin_endpoint_auth_passes_none_when_unauthenticated(self):
        """Verify AdminEndpointAuth returns None when JWTAuth returns None without raising 403."""
        with patch.object(JWTAuth, "authenticate", return_value=None):
            auth = AdminEndpointAuth()
            result = auth.authenticate(HttpRequest(), "fake_token")
            self.assertIsNone(result)
