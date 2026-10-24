from django.test import TestCase
from pydantic import ValidationError

from authentication.schemas import RefreshTokenIn, RegistrationIn


class TestRegistrationInSchema(TestCase):
    def test_registration_in_valid_payload(self):
        """Verify RegistrationIn instantiates cleanly with valid input fields."""
        data = RegistrationIn(
            full_name="Jane Doe",
            email="jane.doe@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        )
        self.assertEqual(data.full_name, "Jane Doe")
        self.assertEqual(data.email, "jane.doe@example.com")

    def test_registration_in_full_name_whitespace_stripped(self):
        """Verify RegistrationIn strips leading and trailing whitespace from full_name."""
        data = RegistrationIn(
            full_name="   Jane Doe   ",
            email="jane@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        )
        self.assertEqual(data.full_name, "Jane Doe")

    def test_registration_in_email_lowercased(self):
        """Verify RegistrationIn normalizes email address to lowercase."""
        data = RegistrationIn(
            full_name="Jane Doe",
            email="JANE.DOE@EXAMPLE.COM",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        )
        self.assertEqual(data.email, "jane.doe@example.com")

    def test_registration_in_password_mismatch_raises_validation_error(self):
        """Verify RegistrationIn check_passwords_match model validator raises ValidationError on mismatch."""
        with self.assertRaises(ValidationError) as ctx:
            RegistrationIn(
                full_name="Jane Doe",
                email="jane@example.com",
                password="StrongPassword123!",
                confirm_password="DifferentPassword123!",
            )
        self.assertIn("Passwords do not match.", str(ctx.exception))


class TestRefreshTokenInSchema(TestCase):
    def test_refresh_token_in_missing_or_empty_raises_validation_error(self):
        """Verify RefreshTokenIn enforces required refresh_token field in isolation."""
        with self.assertRaises(ValidationError):
            RefreshTokenIn()

        with self.assertRaises(ValidationError):
            RefreshTokenIn(refresh_token=None)
