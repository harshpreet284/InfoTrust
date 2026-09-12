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
