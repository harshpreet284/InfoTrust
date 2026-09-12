import json
from django.test import TestCase, Client
from authentication.models import User


class RegistrationAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = '/api/v1/auth/register'
        self.valid_payload = {
            "full_name": "API User",
            "email": "api@example.com",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!"
        }

    def test_registration_success(self):
        """Test successful registration with HTTP 201 and correct payload structure."""
        response = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "Registration successful.")
        
        user_data = data.get("data", {})
        self.assertIn("id", user_data)
        self.assertEqual(user_data.get("full_name"), "API User")
        self.assertEqual(user_data.get("email"), "api@example.com")
        self.assertEqual(user_data.get("role"), "USER")
        self.assertIn("created_at", user_data)
        
        # Verify persistence and hashing
        user = User.objects.get(email="api@example.com")
        self.assertEqual(user.role, "USER")
        self.assertTrue(user.check_password("StrongPassword123!"))
        
        # Verify security - no passwords or sensitive fields exposed
        self.assertNotIn("password", user_data)
        self.assertNotIn("confirm_password", user_data)
        self.assertNotIn("is_superuser", user_data)
        self.assertNotIn("is_staff", user_data)

    def test_duplicate_email(self):
        """Test registering the same email twice returns 409."""
        # First registration
        res1 = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(res1.status_code, 201)
        
        # Second registration
        res2 = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(res2.status_code, 409)
        
        data = res2.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Email already exists.")
        self.assertIn("email", data.get("errors", {}))
        self.assertIn("This email is already registered.", data["errors"]["email"])
        
        # Verify only one user exists
        self.assertEqual(User.objects.filter(email="api@example.com").count(), 1)

    def test_validation_missing_fields(self):
        """Test structural validation failures for missing fields."""
        fields_to_remove = ["full_name", "email", "password", "confirm_password"]
        for field in fields_to_remove:
            payload = self.valid_payload.copy()
            del payload[field]
            
            response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
            self.assertEqual(response.status_code, 422)
            
            data = response.json()
            self.assertIn("detail", data)
            
            # Verify no user created
            self.assertEqual(User.objects.count(), 0)

    def test_validation_password_complexity(self):
        """Test password complexity rules and mismatched confirm_password."""
        invalid_passwords = [
            ("short", "short"), # length < 8
            ("nouppercase1!", "nouppercase1!"), # missing uppercase
            ("NOLOWERCASE1!", "NOLOWERCASE1!"), # missing lowercase
            ("NoNumberHere!", "NoNumberHere!"), # missing number
            ("NoSpecialChar123", "NoSpecialChar123"), # missing special char
            ("StrongPassword123!", "MismatchPassword123!") # mismatch
        ]
        
        for pwd, cpwd in invalid_passwords:
            payload = self.valid_payload.copy()
            payload["password"] = pwd
            payload["confirm_password"] = cpwd
            
            response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
            self.assertEqual(response.status_code, 422)
            self.assertIn("detail", response.json())
            
        self.assertEqual(User.objects.count(), 0)
        
    def test_validation_invalid_email(self):
        """Test invalid email format."""
        payload = self.valid_payload.copy()
        payload["email"] = "not-an-email"
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())
        self.assertEqual(User.objects.count(), 0)

    def test_normalization(self):
        """Test email and name normalization."""
        payload = self.valid_payload.copy()
        payload["full_name"] = "  Spaced Name  "
        payload["email"] = "UPPER@Example.com"
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        
        data = response.json().get("data", {})
        self.assertEqual(data.get("full_name"), "Spaced Name")
        self.assertEqual(data.get("email"), "upper@example.com")
        
        user = User.objects.get(email="upper@example.com")
        self.assertEqual(user.full_name, "Spaced Name")

    def test_security_role_escalation(self):
        """Test that role/is_superuser injection fails and results in USER role."""
        payload = self.valid_payload.copy()
        payload["role"] = "ADMIN"
        payload["is_superuser"] = True
        payload["is_staff"] = True
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        
        data = response.json().get("data", {})
        self.assertEqual(data.get("role"), "USER")
        
        user = User.objects.get(email="api@example.com")
        self.assertEqual(user.role, "USER")
        self.assertFalse(user.is_superuser)

from pydantic import ValidationError
from authentication.schemas import LoginIn

class LoginSerializerTests(TestCase):
    def test_valid_login_payload(self):
        """Test valid email and password succeeds."""
        payload = {"email": "test@example.com", "password": "password123"}
        login_in = LoginIn.model_validate(payload)
        self.assertEqual(login_in.email, "test@example.com")
        self.assertEqual(login_in.password, "password123")
        
    def test_uppercase_email_normalized(self):
        """Test uppercase email is normalized to lowercase."""
        payload = {"email": "UPPER@Example.com", "password": "pwd"}
        login_in = LoginIn.model_validate(payload)
        self.assertEqual(login_in.email, "upper@example.com")
        
    def test_missing_email_fails(self):
        """Test missing email fails validation."""
        payload = {"password": "pwd"}
        with self.assertRaises(ValidationError) as context:
            LoginIn.model_validate(payload)
        self.assertIn("email", str(context.exception))
        
    def test_missing_password_fails(self):
        """Test missing password fails validation."""
        payload = {"email": "test@example.com"}
        with self.assertRaises(ValidationError) as context:
            LoginIn.model_validate(payload)
        self.assertIn("password", str(context.exception))
        
    def test_invalid_email_format(self):
        """Test invalid email format fails validation."""
        payload = {"email": "not-an-email", "password": "pwd"}
        with self.assertRaises(ValidationError) as context:
            LoginIn.model_validate(payload)
        self.assertIn("email", str(context.exception))

import jwt
from django.conf import settings
from authentication.services import authenticate_user
from authentication.exceptions import InvalidCredentialsError, AccountDisabledError

class LoginServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="service@example.com",
            full_name="Service User",
            password="StrongPassword123!"
        )
        
    def test_service_login_success(self):
        payload = LoginIn(email="service@example.com", password="StrongPassword123!")
        result = authenticate_user(payload)
        
        self.assertEqual(result["user"], self.user)
        self.assertTrue(isinstance(result["access_token"], str))
        self.assertTrue(isinstance(result["refresh_token"], str))
        self.assertTrue(len(result["access_token"]) > 0)
        
        # Verify JWT claims
        decoded_access = jwt.decode(result["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(decoded_access["token_type"], "access")
        self.assertEqual(decoded_access["user_id"], str(self.user.id))
        self.assertIn("exp", decoded_access)
        self.assertIn("iat", decoded_access)
        self.assertIn("jti", decoded_access)

    def test_service_login_wrong_email(self):
        payload = LoginIn(email="wrong@example.com", password="StrongPassword123!")
        with self.assertRaises(InvalidCredentialsError) as context:
            authenticate_user(payload)
        self.assertEqual(str(context.exception), "Invalid email or password.")
        
    def test_service_login_wrong_password(self):
        payload = LoginIn(email="service@example.com", password="WrongPassword123!")
        with self.assertRaises(InvalidCredentialsError) as context:
            authenticate_user(payload)
        self.assertEqual(str(context.exception), "Invalid email or password.")
        
    def test_service_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        payload = LoginIn(email="service@example.com", password="StrongPassword123!")
        with self.assertRaises(AccountDisabledError) as context:
            authenticate_user(payload)
        self.assertEqual(str(context.exception), "This account has been disabled.")

class LoginAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = '/api/v1/auth/login'
        self.user = User.objects.create_user(
            email="loginapi@example.com",
            full_name="Login API User",
            password="StrongPassword123!"
        )
        self.valid_payload = {
            "email": "loginapi@example.com",
            "password": "StrongPassword123!"
        }
        
    def test_api_login_success(self):
        response = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "Login successful.")
        
        inner_data = data.get("data", {})
        self.assertIn("access_token", inner_data)
        self.assertIn("refresh_token", inner_data)
        
        user_data = inner_data.get("user", {})
        self.assertEqual(user_data.get("email"), "loginapi@example.com")
        self.assertEqual(user_data.get("full_name"), "Login API User")
        self.assertIn("id", user_data)
        self.assertIn("role", user_data)
        
        # Verify sensitive fields are omitted
        self.assertNotIn("password", user_data)
        self.assertNotIn("is_active", user_data)
        self.assertNotIn("is_superuser", user_data)
        self.assertNotIn("is_staff", user_data)
        
    def test_api_login_wrong_email(self):
        payload = self.valid_payload.copy()
        payload["email"] = "wrong@example.com"
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid email or password.")
        self.assertNotIn("errors", data)
        
    def test_api_login_wrong_password(self):
        payload = self.valid_payload.copy()
        payload["password"] = "wrong"
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid email or password.")
        self.assertNotIn("errors", data)
        
    def test_api_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "This account has been disabled.")
        
    def test_api_login_missing_fields(self):
        payload = {"email": "loginapi@example.com"}
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())

from ninja_jwt.tokens import RefreshToken
from datetime import timedelta
import time

class RefreshTokenAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = '/api/v1/auth/refresh'
        self.user = User.objects.create_user(
            email="refreshapi@example.com",
            full_name="Refresh API User",
            password="StrongPassword123!"
        )
        # Manually create a valid refresh token for the user
        self.refresh = RefreshToken.for_user(self.user)
        self.valid_payload = {
            "refresh_token": str(self.refresh)
        }

    def test_refresh_token_success(self):
        """Test valid refresh returns access_token and rotated refresh_token."""
        response = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "Token refreshed successfully.")
        
        inner_data = data.get("data", {})
        self.assertIn("access_token", inner_data)
        self.assertIn("refresh_token", inner_data)
        
        # Verify it rotated the token
        self.assertNotEqual(inner_data["refresh_token"], self.valid_payload["refresh_token"])

    def test_refresh_token_rotation_and_blacklist(self):
        """Test the original refresh token cannot be reused after rotation."""
        # 1. Refresh successfully once
        response1 = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response1.status_code, 200)
        
        # 2. Attempt to reuse the exact same original refresh token
        response2 = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response2.status_code, 401)
        data = response2.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid or expired refresh token.")

    def test_new_refresh_token_works(self):
        """Test the newly returned rotated refresh token functions correctly."""
        # 1. Refresh successfully once
        response1 = self.client.post(self.url, data=json.dumps(self.valid_payload), content_type="application/json")
        self.assertEqual(response1.status_code, 200)
        new_refresh = response1.json()["data"]["refresh_token"]
        
        # 2. Use the new token for a second refresh
        payload2 = {"refresh_token": new_refresh}
        response2 = self.client.post(self.url, data=json.dumps(payload2), content_type="application/json")
        self.assertEqual(response2.status_code, 200)
        
        data = response2.json()
        self.assertTrue(data.get("success"))
        self.assertIn("access_token", data["data"])

    def test_refresh_token_invalid_format(self):
        """Test a malformed token returns 401 Invalid Token."""
        payload = {"refresh_token": "not-a-valid-jwt"}
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid or expired refresh token.")

    def test_refresh_token_expired(self):
        """Test an expired token returns 401. Force expiration by manually mutating claims."""
        self.refresh.set_exp(lifetime=-timedelta(days=1))
        payload = {"refresh_token": str(self.refresh)}
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid or expired refresh token.")

    def test_refresh_token_missing_fields(self):
        """Test an empty payload returns 422 Native Ninja validation."""
        response = self.client.post(self.url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())

class LogoutAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = '/api/v1/auth/logout'
        self.user = User.objects.create_user(
            email="logout_test@example.com",
            full_name="Logout Test User",
            password="StrongPassword123!"
        )
        self.login_payload = {
            "email": "logout_test@example.com",
            "password": "StrongPassword123!"
        }

    def _get_refresh_token(self):
        response = self.client.post('/api/v1/auth/login', data=json.dumps(self.login_payload), content_type="application/json")
        return response.json().get("data", {}).get("refresh_token")

    def test_logout_success(self):
        """Test successful logout using a valid refresh token."""
        refresh_token = self._get_refresh_token()
        payload = {"refresh_token": refresh_token}
        
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "Logged out successfully.")
        self.assertEqual(data.get("data"), {})

    def test_logout_blacklists_token(self):
        """Test that a logged-out token is successfully blacklisted and rejected by /refresh."""
        refresh_token = self._get_refresh_token()
        payload = {"refresh_token": refresh_token}
        
        # 1. Logout
        logout_res = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(logout_res.status_code, 200)
        
        # 2. Attempt to refresh with blacklisted token
        refresh_res = self.client.post('/api/v1/auth/refresh', data=json.dumps(payload), content_type="application/json")
        self.assertEqual(refresh_res.status_code, 401)
        
        err_data = refresh_res.json()
        self.assertFalse(err_data.get("success"))
        self.assertEqual(err_data.get("message"), "Invalid or expired refresh token.")

    def test_logout_fails_with_invalid_refresh_token(self):
        """Test that a malformed refresh token returns 401 Invalid Token."""
        payload = {"refresh_token": "not.a.valid.jwt"}
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        
        self.assertEqual(response.status_code, 401)
        err_data = response.json()
        self.assertFalse(err_data.get("success"))
        self.assertEqual(err_data.get("message"), "Invalid or expired refresh token.")

    def test_logout_fails_with_already_blacklisted_token(self):
        """Test that attempting to logout twice with the same token returns 401."""
        refresh_token = self._get_refresh_token()
        payload = {"refresh_token": refresh_token}
        
        # 1. Logout successfully
        res1 = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res1.status_code, 200)
        
        # 2. Try to logout again
        res2 = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res2.status_code, 401)
        
        err_data = res2.json()
        self.assertFalse(err_data.get("success"))
        self.assertEqual(err_data.get("message"), "Invalid or expired refresh token.")

    def test_logout_missing_fields(self):
        """Test that missing refresh_token payload field returns 422."""
        response = self.client.post(self.url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())

class CurrentUserAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = '/api/v1/auth/me'
        self.user = User.objects.create_user(
            email="me_test@example.com",
            full_name="Me Test User",
            password="StrongPassword123!"
        )
        self.login_payload = {
            "email": "me_test@example.com",
            "password": "StrongPassword123!"
        }

    def _get_access_token(self):
        response = self.client.post('/api/v1/auth/login', data=json.dumps(self.login_payload), content_type="application/json")
        return response.json().get("data", {}).get("access_token")

    def test_get_current_user_success(self):
        """Test successful retrieval of current user profile."""
        access_token = self._get_access_token()
        headers = {'HTTP_AUTHORIZATION': f'Bearer {access_token}'}
        
        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "User profile retrieved successfully.")
        
        user_data = data.get("data", {})
        self.assertEqual(user_data.get("id"), str(self.user.id))
        self.assertEqual(user_data.get("email"), "me_test@example.com")
        self.assertEqual(user_data.get("full_name"), "Me Test User")
        self.assertEqual(user_data.get("role"), "USER")
        self.assertIn("created_at", user_data)
        self.assertTrue(user_data.get("is_active"))
        
        # Verify sensitive fields are absent
        self.assertNotIn("password", user_data)
        self.assertNotIn("is_superuser", user_data)
        self.assertNotIn("is_staff", user_data)

    def test_get_current_user_unauthorized(self):
        """Test that missing Authorization header returns 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json().get("detail"), "Unauthorized")

    def test_get_current_user_invalid_token(self):
        """Test that invalid Bearer token returns 401."""
        headers = {'HTTP_AUTHORIZATION': 'Bearer invalid.token.here'}
        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_get_current_user_disabled_account(self):
        """Test that a deactivated user's previously issued token returns 401."""
        access_token = self._get_access_token()
        
        # Deactivate user in DB
        self.user.is_active = False
        self.user.save()
        
        headers = {'HTTP_AUTHORIZATION': f'Bearer {access_token}'}
        response = self.client.get(self.url, **headers)
        
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())
